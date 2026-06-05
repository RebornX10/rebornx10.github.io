import json
import time

import pandas as pd
import pytest
from django.test import RequestFactory

from app import server
from app.models import Paper

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


def test_index_renders(monkeypatch):
    monkeypatch.setattr(server, "pick_model", lambda: "llama3.2")
    resp = server.index(rf.get("/"))
    body = resp.content.decode()
    assert resp.status_code == 200
    assert "Global Paper Research Assistant" in body
    assert "llama3.2" in body


def test_index_shows_banner_without_model(monkeypatch):
    monkeypatch.setattr(server, "pick_model", lambda: None)
    body = server.index(rf.get("/")).content.decode()
    assert "ollama pull" in body


def test_build_requires_topic():
    resp = server.build(rf.post("/build", data=json.dumps({}), content_type="application/json"))
    assert resp.status_code == 400


def test_build_rejects_get():
    assert server.build(rf.get("/build")).status_code == 400


def test_build_starts_job(monkeypatch):
    monkeypatch.setattr(server, "fetch_metadata",
                        lambda *a, **k: [Paper(openalex_id="W", doi=None, title="t")])
    monkeypatch.setattr(server, "download_many", lambda papers, **k: papers)
    monkeypatch.setattr(server, "save_corpus", lambda df, *a, **k: None)
    resp = server.build(rf.post("/build", data=json.dumps({"topic": "x", "n": 1}),
                                content_type="application/json"))
    job_id = json.loads(resp.content)["job_id"]
    done = _wait_done(job_id)
    assert done["progress"] == 100
    assert not done["error"]
    assert "df" in server.CORPUS


def test_build_handles_no_results(monkeypatch):
    monkeypatch.setattr(server, "fetch_metadata", lambda *a, **k: [])
    resp = server.build(rf.post("/build", data=json.dumps({"topic": "x"}),
                                content_type="application/json"))
    done = _wait_done(json.loads(resp.content)["job_id"])
    assert done["error"] is True


def test_build_clamps_to_cap(monkeypatch):
    captured = {}

    def fake_run_build(job_id, topic, date_from, date_to, n):
        captured["n"] = n
        server.JOBS[job_id]["done"] = True

    monkeypatch.setattr(server, "run_build", fake_run_build)
    resp = server.build(rf.post("/build", data=json.dumps({"topic": "x", "n": 999999}),
                                content_type="application/json"))
    job_id = json.loads(resp.content)["job_id"]
    _wait_done(job_id)
    assert captured["n"] == server.effective_max_papers()


def test_metrics_endpoint():
    resp = server.metrics_view(rf.get("/metrics"))
    data = json.loads(resp.content)
    for k in ("cpu", "ram", "net_kbps", "ram_used_mb", "ram_total_mb"):
        assert k in data


def test_build_handles_oom(monkeypatch):
    monkeypatch.setattr(server, "fetch_metadata",
                        lambda *a, **k: [Paper(openalex_id="W", doi=None, title="t")])

    def boom(*a, **k):
        raise MemoryError()

    monkeypatch.setattr(server, "download_many", boom)
    resp = server.build(rf.post("/build", data=json.dumps({"topic": "x", "n": 5}),
                                content_type="application/json"))
    done = _wait_done(json.loads(resp.content)["job_id"])
    assert done["error"] is True
    assert "memory" in done["stage"].lower()
    assert done.get("suggested_n", 0) >= 1


def test_status_unknown_job():
    assert server.status(rf.get("/status?job=nope")).status_code == 400


def test_status_known_job():
    server.JOBS["abc"] = {"stage": "x", "progress": 50, "done": False, "error": False}
    resp = server.status(rf.get("/status?job=abc"))
    assert json.loads(resp.content)["progress"] == 50


def test_ask_without_corpus():
    resp = server.ask(rf.post("/ask", data=json.dumps({"question": "q"}),
                              content_type="application/json"))
    assert resp.status_code == 400
    assert "Download a topic" in json.loads(resp.content)["error"]


def test_ask_without_model(monkeypatch):
    server.CORPUS["df"] = pd.DataFrame([{"title": "t", "content": "c"}])
    monkeypatch.setattr(server, "pick_model", lambda: None)
    resp = server.ask(rf.post("/ask", data=json.dumps({"question": "q"}),
                              content_type="application/json"))
    assert resp.status_code == 400


def test_ask_success(monkeypatch):
    server.CORPUS["df"] = pd.DataFrame([
        {"title": "Graphene", "abstract": "graphene", "content": "graphene text",
         "authors": ["A"], "journal": "J", "date": "2023"}])
    monkeypatch.setattr(server, "pick_model", lambda: "llama3.2")
    monkeypatch.setattr(server, "chat", lambda q, c, m: "The answer")
    resp = server.ask(rf.post("/ask", data=json.dumps({"question": "what is graphene"}),
                              content_type="application/json"))
    data = json.loads(resp.content)
    assert data["answer"] == "The answer"
    assert data["sources"][0]["title"] == "Graphene"


def test_ask_handles_ollama_error(monkeypatch):
    server.CORPUS["df"] = pd.DataFrame([{"title": "t", "abstract": "a", "content": "c",
                                         "authors": ["A"], "journal": "J", "date": "2023"}])
    monkeypatch.setattr(server, "pick_model", lambda: "m")

    def boom(*a, **k):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(server, "chat", boom)
    resp = server.ask(rf.post("/ask", data=json.dumps({"question": "q"}),
                              content_type="application/json"))
    assert resp.status_code == 500
