from app import crossref
from app.http import SESSION
from tests.conftest import FakeResponse

PAYLOAD = {
    "message": {
        "next-cursor": None,
        "items": [
            {
                "DOI": "10.1/abc",
                "title": ["Graphene Synthesis"],
                "author": [
                    {"given": "Ada", "family": "Lovelace"},
                    {"family": "Turing"},
                ],
                "issued": {"date-parts": [[2023, 5, 1]]},
                "container-title": ["Journal of Carbon"],
                "abstract": "<jats:p>We make <b>graphene</b>.</jats:p>",
                "subject": ["Materials"],
                "link": [
                    {"URL": "https://x/landing.html", "content-type": "text/html"},
                    {"URL": "https://x/paper.pdf", "content-type": "application/pdf"},
                ],
            },
            {
                "DOI": "10.2/nopdf",
                "title": ["No PDF Article"],
                "author": [],
                "issued": {"date-parts": [[2022]]},
                "container-title": ["Other"],
                "link": [{"URL": "https://y/page.html", "content-type": "text/html"}],
            },
        ],
    }
}


def _patch(monkeypatch, payload=PAYLOAD):
    monkeypatch.setattr(SESSION, "get", lambda *a, **k: FakeResponse(json_data=payload))


def test_crossref_parses_item(monkeypatch):
    _patch(monkeypatch)
    papers = list(crossref.fetch_metadata(5, search="graphene"))
    assert len(papers) == 1  # the no-PDF item is filtered out
    p = papers[0]
    assert p.title == "Graphene Synthesis"
    assert p.authors == ["Ada Lovelace", "Turing"]
    assert p.journal == "Journal of Carbon"
    assert p.date == "2023-05-01"
    assert p.theme == "Materials"
    assert p.doi == "https://doi.org/10.1/abc"
    assert p.pdf_url == "https://x/paper.pdf"
    assert p.abstract == "We make graphene."  # JATS tags stripped


def test_crossref_keeps_nopdf_when_not_required(monkeypatch):
    _patch(monkeypatch)
    papers = list(crossref.fetch_metadata(5, require_pdf=False))
    assert len(papers) == 2
    assert papers[1].pdf_url is None
    assert papers[1].date == "2022-01-01"  # month/day default to 1


def test_crossref_respects_n(monkeypatch):
    _patch(monkeypatch)
    assert len(list(crossref.fetch_metadata(1, require_pdf=False))) == 1
