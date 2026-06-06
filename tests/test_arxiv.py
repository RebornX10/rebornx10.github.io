from app import arxiv
from app.http import SESSION
from tests.conftest import FakeResponse

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <published>2024-01-02T00:00:00Z</published>
    <title>Deep Learning for Graphene</title>
    <summary>We study graphene with neural nets.</summary>
    <author><name>Ada Lovelace</name></author>
    <author><name>Alan Turing</name></author>
    <link rel="alternate" href="http://arxiv.org/abs/2401.00001v1"/>
    <link title="pdf" type="application/pdf" href="http://arxiv.org/pdf/2401.00001v1"/>
    <arxiv:primary_category term="cs.LG"/>
    <arxiv:doi>10.1234/xyz</arxiv:doi>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002v1</id>
    <published>2024-02-03T00:00:00Z</published>
    <title>No PDF Here</title>
    <summary>An entry without a pdf link.</summary>
    <author><name>Grace Hopper</name></author>
    <link rel="alternate" href="http://arxiv.org/abs/2401.00002v1"/>
  </entry>
</feed>"""


class _Resp(FakeResponse):
    def __init__(self, text):
        super().__init__()
        self.text = text


def _patch(monkeypatch, text=ATOM):
    monkeypatch.setattr(SESSION, "get", lambda *a, **k: _Resp(text))


def test_arxiv_parses_entry(monkeypatch):
    _patch(monkeypatch)
    papers = list(arxiv.fetch_metadata(5, search="graphene"))
    assert len(papers) == 2
    p = papers[0]
    assert p.title == "Deep Learning for Graphene"
    assert p.authors == ["Ada Lovelace", "Alan Turing"]
    assert p.journal == "arXiv"
    assert p.date == "2024-01-02"
    assert p.theme == "cs.LG"
    assert p.pdf_url == "http://arxiv.org/pdf/2401.00001v1"
    assert p.doi == "https://doi.org/10.1234/xyz"


def test_arxiv_constructs_pdf_from_abs(monkeypatch):
    _patch(monkeypatch)
    papers = list(arxiv.fetch_metadata(5))
    # second entry had no pdf link -> derived from the /abs/ id
    assert papers[1].pdf_url == "http://arxiv.org/pdf/2401.00002v1"


def test_arxiv_respects_n(monkeypatch):
    _patch(monkeypatch)
    assert len(list(arxiv.fetch_metadata(1))) == 1
