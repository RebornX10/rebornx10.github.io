from __future__ import annotations

import logging
import time
from typing import Iterator, List, Optional

from app.config import CONFIG
from app.http import SESSION
from app.models import Paper

log = logging.getLogger("pubmed")

# We target PubMed Central's open-access subset so a downloadable PDF exists.
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PDF_URL = "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{uid}/pdf/"

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def _date(pubdate: Optional[str]) -> Optional[str]:
    """PMC pubdate is free-form: '2023 May 1', '2023 May', or '2023'."""
    if not pubdate:
        return None
    parts = pubdate.replace("-", " ").split()
    if not parts or not parts[0].isdigit():
        return None
    y = int(parts[0])
    m = _MONTHS.get(parts[1][:3], 1) if len(parts) > 1 else 1
    d = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
    return f"{y:04d}-{m:02d}-{d:02d}"


def _params(extra: dict) -> dict:
    p = {"db": "pmc", "retmode": "json"}
    mail = CONFIG["openalex"].get("mailto")
    if mail:
        p["email"] = mail
        p["tool"] = "sci_paper_llm"
    p.update(extra)
    return p


def _search_ids(search: Optional[str], n: int) -> List[str]:
    term = f"{search} AND open access[filter]" if search else "open access[filter]"
    r = SESSION.get(ESEARCH, params=_params(
        {"term": term, "retmax": min(max(1, n), 200), "sort": "relevance"}), timeout=60)
    r.raise_for_status()
    return ((r.json() or {}).get("esearchresult", {}) or {}).get("idlist", []) or []


def parse_summary(uid: str, rec: dict) -> Paper:
    authors = [a.get("name") for a in rec.get("authors", []) if a.get("name")]
    doi = None
    for aid in rec.get("articleids", []):
        if aid.get("idtype") == "doi" and aid.get("value"):
            doi = aid["value"]
            break
    title = (rec.get("title") or "").rstrip(".") or None
    journal = rec.get("fulljournalname") or rec.get("source")
    pdf = PDF_URL.format(uid=uid)
    return Paper(
        openalex_id=f"PMC{uid}",
        doi=f"https://doi.org/{doi}" if doi else None,
        title=title,
        authors=authors,
        date=_date(rec.get("pubdate") or rec.get("epubdate")),
        journal=journal,
        country=None,
        countries=[],
        abstract=None,  # esummary omits abstracts; full text is fetched from the PDF
        pdf_url=pdf,
        pdf_candidates=[pdf],
        theme=None,
    )


def fetch_metadata(
    n: int = 100,
    *,
    search: Optional[str] = None,
    extra_filters: Optional[str] = None,  # OpenAlex-style date filters not applied (ignored)
    require_pdf: bool = True,
) -> Iterator[Paper]:
    log.info("PubMed/PMC query: term=%s want=%d", search or "(all)", n)
    ids = _search_ids(search, n)
    if not ids:
        return
    time.sleep(0.34)  # NCBI: <= 3 requests/sec without an API key
    r = SESSION.get(ESUMMARY, params=_params({"id": ",".join(ids)}), timeout=60)
    r.raise_for_status()
    result = (r.json() or {}).get("result", {}) or {}
    yielded = 0
    for uid in result.get("uids", ids):
        rec = result.get(uid)
        if not isinstance(rec, dict):
            continue
        paper = parse_summary(uid, rec)
        if require_pdf and not paper.pdf_url:
            continue
        yield paper
        yielded += 1
        if yielded >= n:
            return
