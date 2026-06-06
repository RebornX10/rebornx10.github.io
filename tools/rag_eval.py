"""Lightweight RAG evaluation harness.

Scores retrieval and (optionally) generated answers against a small golden set,
with deterministic, dependency-free metrics so it can run in CI:

  - retrieval_hit_rate: fraction of questions whose expected source is retrieved
  - kw_recall: fraction of expected keywords present (in the answer, or the
    retrieved context when running retrieval-only)

Usage:
  # retrieval-only (no LLM, deterministic)
  python tools/rag_eval.py --corpus papers.parquet --golden tools/eval_golden.example.json
  # full (also generate + score answers via Ollama)
  python tools/rag_eval.py --corpus papers.parquet --golden golden.json --answers
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from app.retrieval import build_context


def _kw_recall(text: str, keywords: list) -> float:
    if not keywords:
        return 1.0
    t = (text or "").lower()
    return sum(1 for k in keywords if k.lower() in t) / len(keywords)


def _hit(sources: list, needle: str) -> bool:
    if not needle:
        return True
    n = needle.lower()
    return any(n in (s.get("title") or "").lower() for s in sources)


def evaluate(df: pd.DataFrame, golden: list, answer_fn=None) -> dict:
    """Run each golden question. `answer_fn(question, context, sources)` returns
    (answer, sources); if omitted, scores the retrieved context (retrieval-only)."""
    rows = []
    for g in golden:
        q = g["question"]
        context, sources = build_context(df, q)
        if answer_fn is not None:
            answer, src2 = answer_fn(q, context, sources)
            sources = src2 or sources
        else:
            answer = context
        rows.append({
            "question": q,
            "retrieval_hit": _hit(sources, g.get("expect_source_contains")),
            "kw_recall": _kw_recall(answer, g.get("expect_any", [])),
            "has_citation": ("[1]" in (answer or "")) if answer_fn is not None else None,
        })
    n = len(rows) or 1
    summary = {
        "n": len(rows),
        "retrieval_hit_rate": round(sum(r["retrieval_hit"] for r in rows) / n, 3),
        "kw_recall": round(sum(r["kw_recall"] for r in rows) / n, 3),
    }
    return {"rows": rows, "summary": summary}


def _ollama_answer(question, context, sources):
    from app.ollama_client import chat, pick_model
    model = pick_model()
    if not model:
        raise SystemExit("no Ollama model installed; run without --answers for retrieval-only")
    return chat(question, context, model), sources


def main() -> None:
    ap = argparse.ArgumentParser(description="RAG evaluation harness")
    ap.add_argument("--corpus", required=True, help="path to a corpus .parquet")
    ap.add_argument("--golden", required=True, help="path to a golden-set .json")
    ap.add_argument("--answers", action="store_true", help="also generate + score answers via Ollama")
    args = ap.parse_args()

    df = pd.read_parquet(args.corpus)
    golden = json.load(open(args.golden))
    result = evaluate(df, golden, _ollama_answer if args.answers else None)

    for r in result["rows"]:
        mark = "✓" if r["retrieval_hit"] else "✗"
        print(f"  [{mark} hit | kw {r['kw_recall']:.2f}] {r['question']}")
    s = result["summary"]
    print(f"\n{s['n']} questions | retrieval hit-rate {s['retrieval_hit_rate']:.0%} "
          f"| keyword recall {s['kw_recall']:.0%}")


if __name__ == "__main__":
    main()
