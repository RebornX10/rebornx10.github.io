from __future__ import annotations

import logging
import time
from typing import Iterator, Optional

from app.config import CONFIG
from app.http import SESSION
from app.models import Paper

log = logging.getLogger("openalex")

API = "https://api.openalex.org/works"

# Only the top-level fields parse_work actually reads — shrinks each page payload
# and speeds JSON decoding (OpenAlex returns ~50 fields per work by default).
SELECT = ",".join([
    "id", "doi", "title", "authorships", "publication_date", "cited_by_count",
    "primary_location", "locations", "abstract_inverted_index", "primary_topic",
])


def reconstruct_abstract(inv_index: Optional[dict]) -> Optional[str]:
    if not inv_index:
        return None
    positions = [(i, word) for word, idxs in inv_index.items() for i in idxs]
    positions.sort()
    return " ".join(w for _, w in positions)


def parse_work(w: dict) -> Paper:
    authors, countries = [], []
    for a in w.get("authorships", []):
        name = (a.get("author") or {}).get("display_name")
        if name:
            authors.append(name)
        for c in a.get("countries", []):
            if c not in countries:
                countries.append(c)

    src = (w.get("primary_location") or {}).get("source") or {}
    topic = (w.get("primary_topic") or {}).get("display_name")

    repo_urls, pub_urls = [], []
    for loc in w.get("locations", []):
        url = loc.get("pdf_url")
        if not url:
            continue
        is_repo = loc.get("host_type") == "repository" or (
            (loc.get("source") or {}).get("type") == "repository"
        )
        (repo_urls if is_repo else pub_urls).append(url)
    seen, candidates = set(), []
    for u in repo_urls + pub_urls:
        if u not in seen:
            seen.add(u)
            candidates.append(u)

    return Paper(
        openalex_id=w.get("id"),
        doi=w.get("doi"),
        title=w.get("title"),
        authors=authors,
        date=w.get("publication_date"),
        journal=src.get("display_name"),
        country=countries[0] if countries else None,
        countries=countries,
        abstract=reconstruct_abstract(w.get("abstract_inverted_index")),
        pdf_url=candidates[0] if candidates else None,
        pdf_candidates=candidates,
        theme=topic,
        cited_by_count=w.get("cited_by_count"),
    )


def fetch_metadata(
    n: int = 100,
    *,
    search: Optional[str] = None,
    extra_filters: Optional[str] = None,
    require_pdf: bool = True,
) -> Iterator[Paper]:
    filters = ["is_oa:true"]
    if require_pdf:
        filters.append("has_fulltext:true")
    if extra_filters:
        filters.append(extra_filters)

    params = {
        "filter": ",".join(filters),
        "select": SELECT,
        "per-page": CONFIG["openalex"]["per_page"],
        "cursor": "*",
        "mailto": CONFIG["openalex"]["mailto"],
    }
    if search:
        params["search"] = search

    log.info("OpenAlex query: filter=%s search=%s want=%d papers",
             params["filter"], search or "(all)", n)
    yielded = 0
    page = 0
    while yielded < n:
        page += 1
        r = SESSION.get(API, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        log.info("OpenAlex page %d: %d results (cursor=%s), %d/%d yielded",
                 page, len(results), str(params["cursor"])[:12], yielded, n)
        if not results:
            return
        for w in results:
            paper = parse_work(w)
            if require_pdf and not paper.pdf_url:
                continue
            yield paper
            yielded += 1
            if yielded >= n:
                return
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            return
        params["cursor"] = cursor
        time.sleep(0.1)  # polite-pool allows ~10 req/s; keep pagination snappy for large N
