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


def test_build_context_returns_sources_metadata():
    ctx, sources = retrieval.build_context(_df(), "graphene")
    assert sources[0]["journal"] == "J"
    assert sources[0]["date"] == "2023"


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
