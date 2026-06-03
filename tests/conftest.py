import io

import fitz
import pytest

from app.models import Paper


def make_pdf_bytes(text="Hello world from a test PDF"):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


class FakeResponse:
    def __init__(self, *, json_data=None, content=b"", headers=None, status=200):
        self._json = json_data
        self._content = content
        self.headers = headers or {}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json

    def iter_content(self, chunk_size):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]

    def close(self):
        pass


@pytest.fixture
def pdf_bytes():
    return make_pdf_bytes()


@pytest.fixture
def paper():
    return Paper(
        openalex_id="W1", doi="10.1/x", title="Graphene synthesis methods",
        authors=["Ada Lovelace", "Alan Turing"], date="2023-01-01",
        journal="Nature", country="GB", countries=["GB"],
        abstract="A study of graphene synthesis and its applications.",
        pdf_url="https://repo.example/a.pdf",
        pdf_candidates=["https://repo.example/a.pdf"],
    )


def make_work(**over):
    work = {
        "id": "W1",
        "doi": "10.1/x",
        "title": "Graphene synthesis methods",
        "publication_date": "2023-01-01",
        "authorships": [
            {"author": {"display_name": "Ada Lovelace"}, "countries": ["GB"]},
            {"author": {"display_name": "Alan Turing"}, "countries": ["GB", "US"]},
        ],
        "primary_location": {"source": {"display_name": "Nature"}},
        "primary_topic": {"display_name": "Graphene research"},
        "abstract_inverted_index": {"Graphene": [0], "study": [1]},
        "locations": [
            {"host_type": "publisher", "pdf_url": "https://pub.example/a.pdf",
             "source": {"type": "journal"}},
            {"host_type": "repository", "pdf_url": "https://repo.example/a.pdf",
             "source": {"type": "repository"}},
        ],
    }
    work.update(over)
    return work
