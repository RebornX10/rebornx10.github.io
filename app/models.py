from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Paper:
    openalex_id: Optional[str]
    doi: Optional[str]
    title: Optional[str]
    authors: list[str] = field(default_factory=list)
    date: Optional[str] = None
    journal: Optional[str] = None
    country: Optional[str] = None
    countries: list[str] = field(default_factory=list)
    abstract: Optional[str] = None
    pdf_url: Optional[str] = None
    pdf_candidates: list[str] = field(default_factory=list)
    content: Optional[str] = None
    theme: Optional[str] = None
