from app import pubmed
from app.http import SESSION
from tests.conftest import FakeResponse

ESEARCH = {"esearchresult": {"idlist": ["111", "222"]}}
ESUMMARY = {
    "result": {
        "uids": ["111", "222"],
        "111": {
            "uid": "111",
            "title": "CRISPR in plants.",
            "pubdate": "2023 May 1",
            "fulljournalname": "Plant Cell",
            "authors": [{"name": "Doudna J"}, {"name": "Charpentier E"}],
            "articleids": [
                {"idtype": "pmid", "value": "999"},
                {"idtype": "doi", "value": "10.5/crispr"},
            ],
        },
        "222": {
            "uid": "222",
            "title": "Gene editing review",
            "pubdate": "2021",
            "source": "Nature",
            "authors": [{"name": "Zhang F"}],
            "articleids": [{"idtype": "pmid", "value": "1000"}],
        },
    }
}


def _patch(monkeypatch, esearch=ESEARCH, esummary=ESUMMARY):
    def fake_get(url, *a, **k):
        data = esearch if "esearch" in url else esummary
        return FakeResponse(json_data=data)
    monkeypatch.setattr(SESSION, "get", fake_get)


def test_pubmed_parses_summary(monkeypatch):
    _patch(monkeypatch)
    papers = list(pubmed.fetch_metadata(5, search="crispr"))
    assert len(papers) == 2
    p = papers[0]
    assert p.title == "CRISPR in plants"  # trailing period stripped
    assert p.authors == ["Doudna J", "Charpentier E"]
    assert p.journal == "Plant Cell"
    assert p.date == "2023-05-01"
    assert p.doi == "https://doi.org/10.5/crispr"
    assert p.openalex_id == "PMC111"
    assert p.pdf_url == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC111/pdf/"


def test_pubmed_year_only_date_and_no_doi(monkeypatch):
    _patch(monkeypatch)
    p = list(pubmed.fetch_metadata(5))[1]
    assert p.date == "2021-01-01"
    assert p.doi is None
    assert p.journal == "Nature"


def test_pubmed_empty_search_returns_nothing(monkeypatch):
    _patch(monkeypatch, esearch={"esearchresult": {"idlist": []}})
    assert list(pubmed.fetch_metadata(5, search="zzz")) == []


def test_pubmed_respects_n(monkeypatch):
    _patch(monkeypatch)
    assert len(list(pubmed.fetch_metadata(1))) == 1
