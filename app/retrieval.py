from __future__ import annotations

import pandas as pd

from app.config import CONFIG

_R = CONFIG["retrieval"]


def _text(v) -> str:
    return v if isinstance(v, str) else ""


def _authors(v) -> list:
    if isinstance(v, (list, tuple)):
        return list(v)
    if hasattr(v, "tolist"):
        return list(v.tolist())
    return []


def build_context(df: pd.DataFrame, question: str, k: int = None, budget: int = None):
    k = k or _R["top_k"]
    budget = budget or _R["context_budget"]
    q_words = {w.lower() for w in question.split() if len(w) > 2}

    def score(row):
        hay = f"{_text(row.get('title'))} {_text(row.get('abstract'))}".lower()
        return sum(hay.count(w) for w in q_words)

    ranked = sorted(df.to_dict("records"), key=score, reverse=True)[:k]
    parts, sources, used = [], [], 0
    for row in ranked:
        body = _text(row.get("content")) or _text(row.get("abstract"))
        block = (
            f"Title: {_text(row.get('title'))}\n"
            f"Authors: {', '.join(_authors(row.get('authors'))[:6])}\n"
            f"Journal: {_text(row.get('journal'))} ({_text(row.get('date'))})\n"
            f"Excerpt: {body[: budget // k]}\n---"
        )
        if used + len(block) > budget:
            break
        parts.append(block)
        used += len(block)
        sources.append({"title": _text(row.get("title")) or None,
                        "journal": _text(row.get("journal")) or None,
                        "date": _text(row.get("date")) or None})
    return "\n".join(parts), sources
