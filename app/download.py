from __future__ import annotations

import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import fitz

from app.config import CONFIG
from app.http import BROWSER_UA, SESSION
from app.models import Paper

log = logging.getLogger("download")

_DL = CONFIG["download"]


def _fetch_pdf_bytes(url: str, deadline: float) -> Optional[bytes]:
    r = SESSION.get(
        url,
        timeout=(_DL["connect_timeout"], _DL["read_timeout"]),
        headers={"User-Agent": BROWSER_UA},
        stream=True,
    )
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "").lower()
    buf, total = bytearray(), 0
    for chunk in r.iter_content(64 * 1024):
        buf += chunk
        total += len(chunk)
        if total == len(chunk) and "pdf" not in ctype and buf[:4] != b"%PDF":
            r.close()
            return None
        if total > _DL["max_pdf_bytes"] or time.monotonic() > deadline:
            r.close()
            break
    return bytes(buf)


def download_fulltext(
    paper: Paper,
    *,
    max_chars: int = _DL["max_chars"],
    deadline_s: float = _DL["paper_deadline_s"],
) -> Paper:
    candidates = paper.pdf_candidates or ([paper.pdf_url] if paper.pdf_url else [])
    deadline = time.monotonic() + deadline_s
    for url in candidates:
        if time.monotonic() > deadline:
            break
        try:
            data = _fetch_pdf_bytes(url, deadline)
            if not data:
                continue
            with fitz.open(stream=io.BytesIO(data), filetype="pdf") as doc:
                text = "\n".join(str(page.get_text()) for page in doc)
            text = text[:max_chars].strip()
            if text:
                paper.content = text
                paper.pdf_url = url
                return paper
        except Exception as e:
            log.warning("download failed for %s: %s", url, e)
    return paper


def download_many(
    papers: list[Paper],
    *,
    workers: int = _DL["workers"],
    progress: Optional[Callable[[int, int, Paper], None]] = None,
) -> list[Paper]:
    total = len(papers)
    if total == 0:
        return papers
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(download_fulltext, p): p for p in papers}
        for fut in as_completed(futures):
            done += 1
            paper = futures[fut]
            try:
                fut.result()
            except Exception as e:
                log.warning("worker failed for %s: %s", paper.title, e)
            if progress:
                progress(done, total, paper)
    return papers
