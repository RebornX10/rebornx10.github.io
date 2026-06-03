import time

from app import download
from app.http import SESSION
from app.models import Paper
from tests.conftest import FakeResponse


def _pdf_response(pdf_bytes):
    return FakeResponse(content=pdf_bytes, headers={"Content-Type": "application/pdf"})


def test_fetch_pdf_bytes_valid(monkeypatch, pdf_bytes):
    monkeypatch.setattr(SESSION, "get", lambda *a, **k: _pdf_response(pdf_bytes))
    data = download._fetch_pdf_bytes("u", time.monotonic() + 10)
    assert data[:4] == b"%PDF"


def test_fetch_pdf_bytes_rejects_html(monkeypatch):
    resp = FakeResponse(content=b"<html>nope</html>", headers={"Content-Type": "text/html"})
    monkeypatch.setattr(SESSION, "get", lambda *a, **k: resp)
    assert download._fetch_pdf_bytes("u", time.monotonic() + 10) is None


def test_fetch_pdf_bytes_byte_cap(monkeypatch):
    monkeypatch.setitem(download._DL, "max_pdf_bytes", 1000)
    big = b"%PDF" + b"0" * 5000
    monkeypatch.setattr(SESSION, "get",
                        lambda *a, **k: FakeResponse(content=big,
                                                     headers={"Content-Type": "application/pdf"}))
    data = download._fetch_pdf_bytes("u", time.monotonic() + 10)
    assert len(data) <= 1000 + 64 * 1024


def test_fetch_pdf_bytes_deadline(monkeypatch):
    data_in = b"%PDF" + b"0" * 200000
    monkeypatch.setattr(SESSION, "get",
                        lambda *a, **k: FakeResponse(content=data_in,
                                                     headers={"Content-Type": "application/pdf"}))
    out = download._fetch_pdf_bytes("u", time.monotonic() - 1)  # already past deadline
    assert out[:4] == b"%PDF"
    assert len(out) <= 64 * 1024


def test_download_fulltext_success(monkeypatch, pdf_bytes, paper):
    monkeypatch.setattr(SESSION, "get", lambda *a, **k: _pdf_response(pdf_bytes))
    download.download_fulltext(paper)
    assert paper.content and "test PDF" in paper.content
    assert paper.pdf_url == "https://repo.example/a.pdf"


def test_download_fulltext_falls_back_to_second_candidate(monkeypatch, pdf_bytes):
    p = Paper(openalex_id="W", doi=None, title="t",
              pdf_candidates=["https://bad/a.pdf", "https://good/a.pdf"])
    calls = []

    def fake_get(url, *a, **k):
        calls.append(url)
        if "bad" in url:
            return FakeResponse(content=b"<html>", headers={"Content-Type": "text/html"})
        return _pdf_response(pdf_bytes)

    monkeypatch.setattr(SESSION, "get", fake_get)
    download.download_fulltext(p)
    assert p.content is not None
    assert p.pdf_url == "https://good/a.pdf"
    assert len(calls) == 2


def test_download_fulltext_all_fail(monkeypatch):
    p = Paper(openalex_id="W", doi=None, title="t", pdf_candidates=["https://bad/a.pdf"])
    monkeypatch.setattr(SESSION, "get",
                        lambda *a, **k: FakeResponse(content=b"x", headers={"Content-Type": "text/html"}))
    download.download_fulltext(p)
    assert p.content is None


def test_download_fulltext_no_candidates():
    p = Paper(openalex_id="W", doi=None, title="t", pdf_candidates=[])
    download.download_fulltext(p)
    assert p.content is None


def test_download_fulltext_handles_exception(monkeypatch):
    p = Paper(openalex_id="W", doi=None, title="t", pdf_candidates=["https://x/a.pdf"])

    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(SESSION, "get", boom)
    download.download_fulltext(p)
    assert p.content is None


def test_download_many_parallel_and_progress(monkeypatch):
    papers = [Paper(openalex_id=f"W{i}", doi=None, title=f"t{i}") for i in range(5)]

    def fake_dl(p, **k):
        p.content = "x"
        return p

    monkeypatch.setattr(download, "download_fulltext", fake_dl)
    seen = []
    download.download_many(papers, workers=3, progress=lambda d, t, p: seen.append((d, t)))
    assert all(p.content == "x" for p in papers)
    assert len(seen) == 5
    assert seen[-1] == (5, 5)


def test_download_many_empty():
    assert download.download_many([]) == []


def test_download_many_survives_worker_error(monkeypatch):
    papers = [Paper(openalex_id="W", doi=None, title="t")]

    def boom(p, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(download, "download_fulltext", boom)
    out = download.download_many(papers, workers=2)
    assert out == papers
