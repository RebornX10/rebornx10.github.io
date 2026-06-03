import pandas as pd

from app import corpus
from app.models import Paper


def _papers(n=3):
    return [Paper(openalex_id=f"W{i}", doi=None, title=f"Paper {i}",
                  authors=["A"], theme="Topic") for i in range(n)]


def test_build_corpus_metadata_only(monkeypatch):
    monkeypatch.setattr(corpus, "fetch_metadata", lambda *a, **k: iter(_papers()))
    called = {}
    monkeypatch.setattr(corpus, "download_many",
                        lambda papers, **k: called.setdefault("dl", True) or papers)
    df = corpus.build_corpus(3, with_fulltext=False, with_theme=False)
    assert len(df) == 3
    assert "dl" not in called
    assert list(df.columns)[:3] == ["authors", "title", "content"]


def test_build_corpus_with_fulltext(monkeypatch):
    monkeypatch.setattr(corpus, "fetch_metadata", lambda *a, **k: iter(_papers()))
    hits = {}

    def fake_dl(papers, **k):
        hits["n"] = len(papers)
        for p in papers:
            p.content = "full text"
        return papers

    monkeypatch.setattr(corpus, "download_many", fake_dl)
    df = corpus.build_corpus(3, with_fulltext=True, with_theme=False)
    assert hits["n"] == 3
    assert (df["content"] == "full text").all()


def test_build_corpus_columns_only_known():
    assert "title" in corpus.COLUMNS and "content" in corpus.COLUMNS


def test_save_corpus_writes_files(tmp_path):
    df = pd.DataFrame([{"title": "x", "content": "y"}])
    base = str(tmp_path / "out")
    corpus.save_corpus(df, base)
    assert (tmp_path / "out.parquet").exists()
    assert (tmp_path / "out.csv").exists()
    assert len(pd.read_parquet(base + ".parquet")) == 1


def test_save_corpus_creates_missing_parent(tmp_path):
    df = pd.DataFrame([{"title": "x", "content": "y"}])
    base = str(tmp_path / "data" / "papers")
    corpus.save_corpus(df, base)
    assert (tmp_path / "data" / "papers.parquet").exists()
