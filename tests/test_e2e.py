import json
import time

import pytest
from django.test import RequestFactory

from app import server
from app.http import SESSION
from app.models import Paper
from tests.conftest import FakeResponse, make_work

rf = RequestFactory()


@pytest.fixture(autouse=True)
def clear_state():
    server.JOBS.clear()
    server.CORPUS.clear()
    yield
    server.JOBS.clear()
    server.CORPUS.clear()


def _wait_done(job_id, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if server.JOBS[job_id]["done"]:
            return server.JOBS[job_id]
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_full_flow_build_then_ask(monkeypatch, pdf_bytes, tmp_path):
    """Build a topic (mocked network) then ask a question (mocked Ollama)."""
    page = {"results": [make_work(), make_work()], "meta": {"next_cursor": None}}

    def fake_get(url, *a, **k):
        if "openalex" in url:
            return FakeResponse(json_data=page)
        return FakeResponse(content=pdf_bytes, headers={"Content-Type": "application/pdf"})

    monkeypatch.setattr(SESSION, "get", fake_get)
    monkeypatch.setattr(server, "save_corpus", lambda df, *a, **k: None)

    build_resp = server.build(rf.post("/build",
                                      data=json.dumps({"topic": "graphene", "n": 2}),
                                      content_type="application/json"))
    job_id = json.loads(build_resp.content)["job_id"]
    done = _wait_done(job_id)
    assert done["progress"] == 100 and not done["error"]

    df = server.CORPUS["df"]
    assert len(df) == 2
    assert df["content"].notna().sum() == 2

    monkeypatch.setattr(server, "pick_model", lambda: "llama3.2")
    monkeypatch.setattr(server, "chat",
                        lambda q, c, m: f"Based on the papers: {c[:10]}")
    ask_resp = server.ask(rf.post("/ask",
                                  data=json.dumps({"question": "what about graphene"}),
                                  content_type="application/json"))
    data = json.loads(ask_resp.content)
    assert "answer" in data
    assert data["model"] == "llama3.2"
    assert len(data["sources"]) >= 1


def test_pipeline_shim_exposes_api():
    import pipeline
    for name in ("build_corpus", "save_corpus", "fetch_metadata",
                 "download_fulltext", "download_many", "Paper"):
        assert hasattr(pipeline, name)
