from __future__ import annotations

import logging
import re
import time
from typing import Iterator, Optional

from app.config import CONFIG
from app.http import SESSION
from app.models import Paper

log = logging.getLogger("crossref")

API = "https://api.crossref.org/works"

# Trim the (large) Crossref records to just the fields parse_item reads.
SELECT = ",".join([
    "DOI", "title", "author", "issued", "published", "published-online",
    "container-title", "abstract", "link", "subject",
])

_TAGS = re.compile(r"<[^>]+>")


def _date(parts: Optional[dict]) -> Optional[str]:
    """Crossref dates look like {"date-parts": [[2023, 5, 1]]} (month/day optional)."""
    try:
        dp = (parts or {}).get("date-parts") or []
        if not dp or not dp[0]:
            return None
        y, *rest = dp[0]
        m = rest[0] if len(rest) >= 1 and rest[0] else 1
        d = rest[1] if len(rest) >= 2 and rest[1] else 1
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except Exception:
        return None


def _clean_abstract(a: Optional[str]) -> Optional[str]:
    if not a:
        return None
    # Crossref abstracts are JATS XML; strip the markup crudely.
    txt = _TAGS.sub(" ", a)
    txt = re.sub(r"\s+", " ", txt)
    txt = re.sub(r"\s+([.,;:!?])", r"\1", txt).strip()
    return txt or None


def _first(seq) -> Optional[str]:
    return seq[0] if seq else None


def parse_item(it: dict) -> Paper:
    doi = it.get("DOI")
    authors = []
    for a in it.get("author", []) or []:
        name = " ".join(x for x in [a.get("given"), a.get("family")] if x).strip()
        if name:
            authors.append(name)

    pdfs = []
    for link in it.get("link", []) or []:
        url = link.get("URL")
        if url and link.get("content-type") == "application/pdf" and url not in pdfs:
            pdfs.append(url)

    date = (_date(it.get("issued")) or _date(it.get("published"))
            or _date(it.get("published-online")))
    doi_url = f"https://doi.org/{doi}" if doi else None
    return Paper(
        openalex_id=doi_url,
        doi=doi_url,
        title=_first(it.get("title")),
        authors=authors,
        date=date,
        journal=_first(it.get("container-title")),
        country=None,
        countries=[],
        abstract=_clean_abstract(it.get("abstract")),
        pdf_url=_first(pdfs),
        pdf_candidates=pdfs,
        theme=_first(it.get("subject")),
    )


def fetch_metadata(
    n: int = 100,
    *,
    search: Optional[str] = None,
    extra_filters: Optional[str] = None,  # OpenAlex-style date filters not applied (ignored)
    require_pdf: bool = True,
) -> Iterator[Paper]:
    # Prefer indexed full text; we still keep only items exposing an open PDF link.
    filt = "has-full-text:true" if require_pdf else None
    params = {
        "select": SELECT,
        "rows": 100,
        "cursor": "*",
        "mailto": CONFIG["openalex"]["mailto"],
    }
    if search:
        params["query"] = search
    if filt:
        params["filter"] = filt

    log.info("Crossref query: q=%s filter=%s want=%d", search or "(all)", filt, n)
    yielded = 0
    page = 0
    while yielded < n and page < 50:  # bound deep paging to find PDF-bearing items
        page += 1
        r = SESSION.get(API, params=params, timeout=60)
        r.raise_for_status()
        msg = (r.json() or {}).get("message", {})
        items = msg.get("items", [])
        log.info("Crossref page %d: %d items, %d/%d yielded", page, len(items), yielded, n)
        if not items:
            return
        for it in items:
            paper = parse_item(it)
            if require_pdf and not paper.pdf_url:
                continue
            yield paper
            yielded += 1
            if yielded >= n:
                return
        cursor = msg.get("next-cursor")
        if not cursor:
            return
        params["cursor"] = cursor
        time.sleep(0.1)  # polite to the public pool
