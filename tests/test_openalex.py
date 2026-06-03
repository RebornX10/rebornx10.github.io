import pytest

from app import openalex
from app.http import SESSION
from tests.conftest import FakeResponse, make_work


def test_reconstruct_abstract_orders_words():
    inv = {"world": [1], "hello": [0]}
    assert openalex.reconstruct_abstract(inv) == "hello world"


def test_reconstruct_abstract_empty():
    assert openalex.reconstruct_abstract(None) is None
    assert openalex.reconstruct_abstract({}) is None


def test_parse_work_extracts_fields():
    p = openalex.parse_work(make_work())
    assert p.title == "Graphene synthesis methods"
    assert p.authors == ["Ada Lovelace", "Alan Turing"]
    assert p.journal == "Nature"
    assert p.theme == "Graphene research"
    assert p.country == "GB"
    assert p.countries == ["GB", "US"]


def test_parse_work_prefers_repository_pdf():
    p = openalex.parse_work(make_work())
    assert p.pdf_url == "https://repo.example/a.pdf"
    assert p.pdf_candidates[0] == "https://repo.example/a.pdf"
    assert "https://pub.example/a.pdf" in p.pdf_candidates


def test_parse_work_dedups_candidates():
    work = make_work(locations=[
        {"host_type": "repository", "pdf_url": "https://x/a.pdf",
         "source": {"type": "repository"}},
        {"host_type": "repository", "pdf_url": "https://x/a.pdf",
         "source": {"type": "repository"}},
    ])
    p = openalex.parse_work(work)
    assert p.pdf_candidates == ["https://x/a.pdf"]


def test_parse_work_no_pdf():
    p = openalex.parse_work(make_work(locations=[]))
    assert p.pdf_url is None
    assert p.pdf_candidates == []


def test_fetch_metadata_yields_and_stops(monkeypatch):
    page = {"results": [make_work(), make_work()], "meta": {"next_cursor": None}}
    monkeypatch.setattr(SESSION, "get", lambda *a, **k: FakeResponse(json_data=page))
    out = list(openalex.fetch_metadata(2))
    assert len(out) == 2


def test_fetch_metadata_respects_n(monkeypatch):
    page = {"results": [make_work() for _ in range(5)], "meta": {"next_cursor": "c"}}
    monkeypatch.setattr(SESSION, "get", lambda *a, **k: FakeResponse(json_data=page))
    out = list(openalex.fetch_metadata(3))
    assert len(out) == 3


def test_fetch_metadata_skips_papers_without_pdf(monkeypatch):
    page = {"results": [make_work(locations=[]), make_work()],
            "meta": {"next_cursor": None}}
    monkeypatch.setattr(SESSION, "get", lambda *a, **k: FakeResponse(json_data=page))
    out = list(openalex.fetch_metadata(5))
    assert len(out) == 1


def test_fetch_metadata_empty_results(monkeypatch):
    monkeypatch.setattr(SESSION, "get",
                        lambda *a, **k: FakeResponse(json_data={"results": []}))
    assert list(openalex.fetch_metadata(5)) == []
