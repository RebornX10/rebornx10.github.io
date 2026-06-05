import pandas as pd

from app import retrieval


def _df():
    return pd.DataFrame([
        {"title": "Graphene electronics", "abstract": "graphene transistors",
         "content": "graphene content " * 50, "authors": ["A"], "journal": "J", "date": "2023"},
        {"title": "Cooking pasta", "abstract": "boiling water",
         "content": "pasta " * 50, "authors": ["B"], "journal": "K", "date": "2022"},
    ])


def test_build_context_ranks_relevant_first():
    ctx, sources = retrieval.build_context(_df(), "graphene transistors")
    assert sources[0]["title"] == "Graphene electronics"


def test_build_context_ranks_on_full_content():
    # the matching term lives ONLY in `content` (not title/abstract) -> BM25 over
    # full text must still surface it first. (3 docs so the term's IDF is > 0.)
    df = pd.DataFrame([
        {"title": "Paper A", "abstract": "unrelated", "content": "nothing relevant here " * 20,
         "authors": ["A"], "journal": "J", "date": "2023"},
        {"title": "Paper B", "abstract": "unrelated", "content": "mitochondria " * 40,
         "authors": ["B"], "journal": "K", "date": "2022"},
        {"title": "Paper C", "abstract": "unrelated", "content": "completely different topic " * 20,
         "authors": ["C"], "journal": "L", "date": "2021"},
    ])
    ctx, sources = retrieval.build_context(df, "mitochondria")
    assert sources[0]["title"] == "Paper B"


def test_build_context_returns_sources_metadata():
    ctx, sources = retrieval.build_context(_df(), "graphene")
    assert sources[0]["journal"] == "J"
    assert sources[0]["date"] == "2023"


def test_rerank_reorders_by_embedding(monkeypatch):
    import app.ollama_client as oc
    df = pd.DataFrame([
        {"title": "Doc A", "abstract": "alpha", "content": "alpha " * 30,
         "authors": ["A"], "journal": "J", "date": "2023"},
        {"title": "Doc B", "abstract": "beta", "content": "beta " * 30,
         "authors": ["B"], "journal": "K", "date": "2022"}])
    monkeypatch.setattr(retrieval, "_embeddings_enabled", lambda: True)

    def fake_embed(texts, model):
        # query (texts[0]) is most similar to Doc B
        return [[1.0, 0.0] if not t.startswith("Doc A") else [0.0, 1.0] for t in texts]

    monkeypatch.setattr(oc, "embed", fake_embed)
    ctx, sources = retrieval.build_context(df, "alpha beta", k=2)
    assert sources[0]["title"] == "Doc B"


def test_rerank_falls_back_on_error(monkeypatch):
    import app.ollama_client as oc
    monkeypatch.setattr(retrieval, "_embeddings_enabled", lambda: True)

    def boom(texts, model):
        raise RuntimeError("no embedding server")

    monkeypatch.setattr(oc, "embed", boom)
    ctx, sources = retrieval.build_context(_df(), "graphene transistors")
    assert sources[0]["title"] == "Graphene electronics"  # BM25 result still returned


def test_build_context_respects_budget():
    ctx, sources = retrieval.build_context(_df(), "graphene", k=2, budget=200)
    assert len(ctx) <= 400


def test_build_context_falls_back_to_abstract():
    df = pd.DataFrame([{"title": "T", "abstract": "abstract text", "content": None,
                        "authors": ["A"], "journal": "J", "date": "2023"}])
    ctx, sources = retrieval.build_context(df, "abstract")
    assert "abstract text" in ctx


def test_build_context_handles_nan_values():
    df = pd.DataFrame([{"title": "Graphene", "abstract": float("nan"),
                        "content": float("nan"), "authors": float("nan"),
                        "journal": float("nan"), "date": float("nan")}])
    ctx, sources = retrieval.build_context(df, "graphene")
    assert sources[0]["title"] == "Graphene"
    assert sources[0]["journal"] is None


def test_build_context_handles_numpy_authors(tmp_path):
    df = pd.DataFrame([{"title": "Graphene", "abstract": "graphene study",
                        "content": "graphene text", "authors": ["Ada", "Alan"],
                        "journal": "Nature", "date": "2023"}])
    path = tmp_path / "p.parquet"
    df.to_parquet(path)
    reloaded = pd.read_parquet(path)  # authors comes back as a numpy array
    ctx, sources = retrieval.build_context(reloaded, "graphene")
    assert "Ada" in ctx
    assert sources[0]["title"] == "Graphene"
