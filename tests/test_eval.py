import pandas as pd

from tools import rag_eval as ev


def test_kw_recall():
    assert ev._kw_recall("alpha beta", ["alpha", "gamma"]) == 0.5
    assert ev._kw_recall("anything", []) == 1.0


def test_hit():
    sources = [{"title": "Malaria vaccine efficacy"}, {"title": "Other"}]
    assert ev._hit(sources, "malaria") is True
    assert ev._hit(sources, "dengue") is False
    assert ev._hit(sources, "") is True


def test_evaluate_retrieval_only():
    df = pd.DataFrame([
        {"title": "Malaria vaccine efficacy", "abstract": "RTS,S",
         "content": "The vaccine showed strong efficacy. " * 5,
         "authors": ["A"], "journal": "J", "date": "2023"},
        {"title": "Mosquito nets", "abstract": "bed nets",
         "content": "Insecticide-treated nets cut transmission. " * 5,
         "authors": ["B"], "journal": "K", "date": "2022"},
        {"title": "Unrelated dengue", "abstract": "dengue",
         "content": "dengue and climate. " * 5, "authors": ["C"], "journal": "L", "date": "2021"}])
    golden = [{"question": "malaria vaccine efficacy", "expect_any": ["efficacy"],
               "expect_source_contains": "Malaria"}]
    res = ev.evaluate(df, golden)
    assert res["summary"]["n"] == 1
    assert res["summary"]["retrieval_hit_rate"] == 1.0
    assert res["summary"]["kw_recall"] == 1.0


def test_evaluate_with_answer_fn():
    df = pd.DataFrame([{"title": "T", "abstract": "a", "content": "c",
                        "authors": ["A"], "journal": "J", "date": "2023"}])
    golden = [{"question": "q", "expect_any": ["answer"]}]
    res = ev.evaluate(df, golden, answer_fn=lambda q, c, s: ("the answer [1]", s))
    assert res["rows"][0]["kw_recall"] == 1.0
    assert res["rows"][0]["has_citation"] is True
