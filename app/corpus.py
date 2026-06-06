from __future__ import annotations

import glob
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict
from typing import Optional

import pandas as pd

from app.config import CONFIG
from app.download import download_many
from app.openalex import fetch_metadata
from app.theme import tag_theme

log = logging.getLogger("corpus")

COLUMNS = ["authors", "title", "content", "date", "country", "journal", "theme",
           "cited_by_count", "doi", "openalex_id", "abstract", "pdf_url", "countries"]


def build_corpus(
    n: int = 25,
    *,
    search: Optional[str] = None,
    extra_filters: Optional[str] = None,
    with_fulltext: bool = True,
    with_theme: bool = False,
    workers: Optional[int] = None,
) -> pd.DataFrame:
    client = None
    if with_theme:
        import anthropic
        client = anthropic.Anthropic()

    papers = list(fetch_metadata(n, search=search, extra_filters=extra_filters))

    if with_fulltext:
        download_many(papers, workers=workers)

    if with_theme:
        for paper in papers:
            try:
                tag_theme(paper, client)
            except Exception as e:
                log.warning("theme tagging failed: %s", e)

    df = pd.DataFrame([asdict(p) for p in papers])
    return df.loc[:, [c for c in COLUMNS if c in df.columns]]


def save_corpus(df: pd.DataFrame, out: Optional[str] = None) -> None:
    out = out or CONFIG["download"]["output_basename"]
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    df.to_parquet(f"{out}.parquet")
    df.to_csv(f"{out}.csv", index=False)


# --- corpus cache: skip OpenAlex + re-download when the same request repeats ---

def _cache_dir() -> str:
    base = CONFIG["download"]["output_basename"]
    d = os.path.join(os.path.dirname(base) or ".", "corpora_cache")
    os.makedirs(d, exist_ok=True)
    return d


def cache_key(topic: str, date_from: str, date_to: str, n: int) -> str:
    raw = f"{(topic or '').strip().lower()}|{date_from}|{date_to}|{n}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def save_to_cache(key: str, df: pd.DataFrame, topic: str) -> None:
    d = _cache_dir()
    df.to_parquet(os.path.join(d, f"{key}.parquet"))
    meta = {"key": key, "topic": topic, "count": int(len(df)), "created": time.time()}
    with open(os.path.join(d, f"{key}.json"), "w") as f:
        json.dump(meta, f)


def load_from_cache(key: str) -> Optional[pd.DataFrame]:
    p = os.path.join(_cache_dir(), f"{key}.parquet")
    if os.path.exists(p):
        try:
            return pd.read_parquet(p)
        except Exception as e:
            log.warning("corpus cache read failed (%s): %s", key, e)
    return None


def load_last() -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Most recently cached corpus, for resuming after a restart/reload."""
    metas = sorted(glob.glob(os.path.join(_cache_dir(), "*.json")),
                   key=os.path.getmtime, reverse=True)
    for m in metas:
        try:
            meta = json.load(open(m))
            df = load_from_cache(meta["key"])
            if df is not None:
                return df, meta.get("topic")
        except Exception:
            continue
    return None, None


def list_cached() -> list:
    """All cached corpora (newest first) for the topic switcher."""
    out = []
    for m in glob.glob(os.path.join(_cache_dir(), "*.json")):
        try:
            meta = json.load(open(m))
            out.append({"key": meta["key"], "topic": meta.get("topic", ""),
                        "count": int(meta.get("count", 0)),
                        "created": meta.get("created", os.path.getmtime(m))})
        except Exception:
            continue
    out.sort(key=lambda x: x["created"], reverse=True)
    return out


def load_with_topic(key: str) -> tuple[Optional[pd.DataFrame], str]:
    df = load_from_cache(key)
    if df is None:
        return None, ""
    topic = ""
    p = os.path.join(_cache_dir(), f"{key}.json")
    if os.path.exists(p):
        try:
            topic = json.load(open(p)).get("topic", "")
        except Exception:
            pass
    return df, topic
