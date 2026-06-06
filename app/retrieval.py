from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections import defaultdict

import pandas as pd
from rank_bm25 import BM25Okapi

from app.config import CONFIG

log = logging.getLogger("retrieval")
_R = CONFIG["retrieval"]
_TOKEN = re.compile(r"[a-z0-9]+")
_embed_ok = {"checked": False, "ok": False}


def _text(v) -> str:
    return v if isinstance(v, str) else ""


def _authors(v) -> list:
    if isinstance(v, (list, tuple)):
        return list(v)
    if hasattr(v, "tolist"):
        return list(v.tolist())
    return []


def _tok(s: str) -> list:
    return _TOKEN.findall(s.lower())


def _chunks(text: str, size: int, overlap: int) -> list:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    step = max(1, size - overlap)
    return [text[i:i + size] for i in range(0, len(text), step)]


# The BM25 index is over passages (a title+abstract unit plus content chunks), so
# retrieval can find the relevant part of a long paper. Cached per corpus (the
# DataFrame is replaced wholesale on each build, so its identity is a safe key).
_cache: dict = {"id": None, "df": None, "bm25": None, "rows": None,
                "owners": None, "ctext": None}


def _index(df: pd.DataFrame):
    if _cache["id"] == id(df) and _cache["bm25"] is not None:
        return _cache["bm25"], _cache["rows"], _cache["owners"], _cache["ctext"]
    rows = df.to_dict("records")
    chunked = _R.get("chunk", True)
    size, overlap = _R.get("chunk_size", 1200), _R.get("chunk_overlap", 200)
    tokens, owners, ctext = [], [], []
    for ri, r in enumerate(rows):
        head = f"{_text(r.get('title'))}. {_text(r.get('abstract'))}".strip()
        body = _text(r.get("content"))
        if chunked:
            units = ([head] if head else []) + _chunks(body, size, overlap)
        else:
            units = [f"{head} {body}".strip()]
        if not units:
            units = ["_"]
        for u in units:
            tokens.append(_tok(u) or ["_"])
            owners.append(ri)
            ctext.append(u)
    bm25 = BM25Okapi(tokens)
    _cache.update(id=id(df), df=df, bm25=bm25, rows=rows, owners=owners, ctext=ctext)
    return bm25, rows, owners, ctext


def _best_excerpt(text: str, q_tokens: set, size: int) -> str:
    if len(text) <= size:
        return text.strip()
    step = max(1, size // 2)
    best, best_start, best_score = text[:size], 0, -1
    for start in range(0, len(text) - size + 1, step):
        window = text[start:start + size].lower()
        score = sum(window.count(t) for t in q_tokens)
        if score > best_score:
            best_score, best_start, best = score, start, text[start:start + size]
    return f"{'…' if best_start else ''}{best.strip()}{'…' if best_start + size < len(text) else ''}"


# --- embedding re-rank (optional) with a persistent, content-addressed cache ----

def _embeddings_enabled() -> bool:
    mode = _R.get("rerank", "auto")
    if mode == "off":
        return False
    if mode == "on":
        return True
    if not _embed_ok["checked"]:  # auto: enable only if the embed model is installed
        from app.ollama_client import list_models
        want = (_R.get("embed_model", "nomic-embed-text") or "").split(":")[0]
        _embed_ok["ok"] = bool(want) and any(want in m for m in list_models())
        _embed_ok["checked"] = True
    return _embed_ok["ok"]


_emb_store = None


def _emb_path() -> str:
    from app.corpus import _cache_dir
    return os.path.join(_cache_dir(), "embeddings.json")


def _embed_docs(texts: list, model: str) -> list:
    """Embed document texts, reusing a persistent content-addressed cache so the
    same paper isn't re-embedded across questions or sessions."""
    global _emb_store
    if _emb_store is None:
        try:
            _emb_store = json.load(open(_emb_path()))
        except Exception:
            _emb_store = {}
    keys = [hashlib.sha1(t.encode()).hexdigest() for t in texts]
    missing = [(i, t) for i, (k, t) in enumerate(zip(keys, texts)) if k not in _emb_store]
    if missing:
        from app.ollama_client import embed
        vecs = embed([t for _, t in missing], model)
        for (i, _), v in zip(missing, vecs):
            _emb_store[keys[i]] = v
        try:
            json.dump(_emb_store, open(_emb_path(), "w"))
        except Exception:
            pass
    return [_emb_store[k] for k in keys]


def _rerank(question: str, rows: list, idxs: list) -> list:
    import numpy as np

    from app.ollama_client import embed
    model = _R.get("embed_model", "nomic-embed-text")
    texts = []
    for i in idxs:
        r = rows[i]
        body = _text(r.get("abstract")) or _text(r.get("content"))
        texts.append(f"{_text(r.get('title'))}. {body[:500]}".strip() or "_")
    doc_vecs = _embed_docs(texts, model)
    q_vec = embed([question], model)[0]            # query embedded fresh (not cached)
    M = np.asarray([q_vec] + doc_vecs, dtype="float32")
    q, docs = M[0], M[1:]
    q /= (np.linalg.norm(q) + 1e-9)
    docs /= (np.linalg.norm(docs, axis=1, keepdims=True) + 1e-9)
    order = np.argsort(-(docs @ q))
    return [idxs[j] for j in order]


def _expand(question: str) -> list:
    if not _R.get("multi_query"):
        return []
    try:
        from app.ollama_client import expand_query, pick_model
        model = pick_model()
        return expand_query(question, model, _R.get("mq_count", 3)) if model else []
    except Exception as e:
        log.warning("multi-query expansion failed: %s", e)
        return []


def build_context(df: pd.DataFrame, question: str, k: int = None, budget: int = None):
    k = k or _R["top_k"]
    budget = budget or _R["context_budget"]
    bm25, rows, owners, ctext = _index(df)
    cand_k = max(k, _R.get("rerank_k", 30))

    # Reciprocal-rank-fuse the original question with any LLM-expanded variants.
    # The best-matching passage per paper is tracked for the excerpt.
    queries = [question] + _expand(question)
    fused: dict = defaultdict(float)
    best_chunk: dict = {}
    for q in queries:
        scores = bm25.get_scores(_tok(q) or ["_"])
        per: dict = {}
        for ci, s in enumerate(scores):
            ri = owners[ci]
            if ri not in per or s > per[ri][0]:
                per[ri] = (s, ci)
            if ri not in best_chunk or s > best_chunk[ri][0]:
                best_chunk[ri] = (s, ci)
        for rank, ri in enumerate(sorted(per, key=lambda r: per[r][0], reverse=True)[:50]):
            fused[ri] += 1.0 / (60 + rank)

    cand = sorted(fused, key=lambda r: fused[r], reverse=True)[:cand_k]
    order = cand
    if _embeddings_enabled() and len(cand) > 1:
        try:
            order = _rerank(question, rows, cand)
        except Exception as e:
            log.warning("embedding re-rank failed, falling back to BM25: %s", e)
            order = cand
    order = order[:k]

    q_set = set(_tok(question) or ["_"])
    per_excerpt = max(200, budget // max(1, k))
    parts, sources, used = [], [], 0
    for ri in order:
        row = rows[ri]
        authors = _authors(row.get("authors"))
        idx = len(parts) + 1
        excerpt = _best_excerpt(ctext[best_chunk[ri][1]], q_set, per_excerpt)
        block = (
            f"[{idx}] Title: {_text(row.get('title'))}\n"
            f"Authors: {', '.join(authors[:6])}\n"
            f"Journal: {_text(row.get('journal'))} ({_text(row.get('date'))})\n"
            f"Excerpt: {excerpt}\n---"
        )
        if used + len(block) > budget and parts:
            break
        parts.append(block)
        used += len(block)
        body = _text(row.get("content")) or _text(row.get("abstract"))
        sources.append({"title": _text(row.get("title")) or None,
                        "authors": authors[:6],
                        "journal": _text(row.get("journal")) or None,
                        "date": _text(row.get("date")) or None,
                        "snippet": (body[:240].strip() or None)})
    return "\n".join(parts), sources
