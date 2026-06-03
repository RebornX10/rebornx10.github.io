from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Optional

import pandas as pd

from app.config import CONFIG
from app.download import download_many
from app.openalex import fetch_metadata
from app.theme import tag_theme

log = logging.getLogger("corpus")

COLUMNS = ["authors", "title", "content", "date", "country", "journal", "theme",
           "doi", "openalex_id", "abstract", "pdf_url", "countries"]


def build_corpus(
    n: int = 25,
    *,
    search: Optional[str] = None,
    extra_filters: Optional[str] = None,
    with_fulltext: bool = True,
    with_theme: bool = False,
    workers: int = CONFIG["download"]["workers"],
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
