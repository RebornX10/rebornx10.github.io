from __future__ import annotations

import logging
import time
from typing import Iterator, Optional
from xml.etree import ElementTree as ET

from app.http import SESSION
from app.models import Paper

log = logging.getLogger("arxiv")

API = "http://export.arxiv.org/api/query"
_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _text(el) -> Optional[str]:
    return el.text.strip() if el is not None and el.text else None


def parse_entry(e) -> Paper:
    title = _text(e.find("a:title", _NS))
    summary = _text(e.find("a:summary", _NS))
    published = _text(e.find("a:published", _NS))
    authors = [_text(a.find("a:name", _NS)) for a in e.findall("a:author", _NS)]
    authors = [a for a in authors if a]

    pdf = None
    for link in e.findall("a:link", _NS):
        if link.get("title") == "pdf" or link.get("type") == "application/pdf":
            pdf = link.get("href")
            break
    abs_id = _text(e.find("a:id", _NS))
    if not pdf and abs_id:
        pdf = abs_id.replace("/abs/", "/pdf/")

    cat = e.find("arxiv:primary_category", _NS)
    doi = _text(e.find("arxiv:doi", _NS))
    return Paper(
        openalex_id=abs_id,
        doi=f"https://doi.org/{doi}" if doi else None,
        title=title,
        authors=authors,
        date=published[:10] if published else None,
        journal="arXiv",
        country=None,
        countries=[],
        abstract=summary,
        pdf_url=pdf,
        pdf_candidates=[pdf] if pdf else [],
        theme=cat.get("term") if cat is not None else None,
    )


def fetch_metadata(
    n: int = 100,
    *,
    search: Optional[str] = None,
    extra_filters: Optional[str] = None,  # date filters not supported by the arXiv API (ignored)
    require_pdf: bool = True,
) -> Iterator[Paper]:
    query = f"all:{search}" if search else "all:*"
    params = {"search_query": query, "start": 0, "max_results": min(max(1, n), 300),
              "sortBy": "relevance", "sortOrder": "descending"}
    log.info("arXiv query: %s want=%d", query, n)
    r = SESSION.get(API, params=params, timeout=60)
    if r.status_code == 429:  # arXiv asks for spacing between requests
        time.sleep(3)
        r = SESSION.get(API, params=params, timeout=60)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    yielded = 0
    for e in root.findall("a:entry", _NS):
        paper = parse_entry(e)
        if require_pdf and not paper.pdf_url:
            continue
        yield paper
        yielded += 1
        if yielded >= n:
            return
