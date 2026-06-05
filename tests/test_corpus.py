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


def test_corpus_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setitem(corpus.CONFIG["download"], "output_basename", str(tmp_path / "papers"))
    df = pd.DataFrame([{"title": "T", "content": "c"}])
    key = corpus.cache_key("malaria", "", "", 25)
    assert corpus.load_from_cache(key) is None        # miss before save
    corpus.save_to_cache(key, df, "malaria")
    back = corpus.load_from_cache(key)                  # hit after save
    assert back is not None and len(back) == 1
    last_df, last_topic = corpus.load_last()
    assert last_topic == "malaria" and len(last_df) == 1


def test_list_cached_and_load_with_topic(tmp_path, monkeypatch):
    monkeypatch.setitem(corpus.CONFIG["download"], "output_basename", str(tmp_path / "papers"))
    corpus.save_to_cache(corpus.cache_key("a", "", "", 10), pd.DataFrame([{"title": "x"}]), "alpha")
    corpus.save_to_cache(corpus.cache_key("b", "", "", 10), pd.DataFrame([{"title": "y"}]), "beta")
    topics = {i["topic"] for i in corpus.list_cached()}
    assert {"alpha", "beta"} <= topics
    df, topic = corpus.load_with_topic(corpus.cache_key("a", "", "", 10))
    assert topic == "alpha" and len(df) == 1


def test_cache_key_is_request_specific():
    a = corpus.cache_key("malaria", "", "", 25)
    assert a == corpus.cache_key("Malaria", "", "", 25)   # case-insensitive topic
    assert a != corpus.cache_key("malaria", "", "", 50)   # n matters
