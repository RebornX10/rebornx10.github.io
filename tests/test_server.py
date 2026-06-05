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


def test_index_uses_external_assets(monkeypatch):
    monkeypatch.setattr(server, "pick_model", lambda: "llama3.2")
    body = server.index(rf.get("/")).content.decode()
    assert "/static/styles.css" in body and "/static/app.js" in body
    assert "<style>" not in body and "<script>" not in body


def test_static_assets_served():
    css = server.app_css(rf.get("/static/styles.css"))
    js = server.app_js(rf.get("/static/app.js"))
    assert css.status_code == 200 and css["Content-Type"] == "text/css"
    assert b":root" in css.content
    assert js.status_code == 200 and "javascript" in js["Content-Type"]
    assert b"pollMetrics" in js.content


def test_index_has_pwa_meta(monkeypatch):
    monkeypatch.setattr(server, "pick_model", lambda: "llama3.2")
    body = server.index(rf.get("/")).content.decode()
    assert "/manifest.webmanifest" in body
    assert 'name="theme-color"' in body
    assert "apple-touch-icon" in body


def test_manifest_served():
    resp = server.manifest_view(rf.get("/manifest.webmanifest"))
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/manifest+json"
    data = json.loads(resp.content)
    assert data["display"] == "standalone"
    assert any(i["sizes"] == "512x512" for i in data["icons"])
    assert any(i.get("purpose") == "maskable" for i in data["icons"])


def test_service_worker_served():
    resp = server.sw_js(rf.get("/sw.js"))
    assert resp.status_code == 200
    assert "javascript" in resp["Content-Type"]
    assert resp["Service-Worker-Allowed"] == "/"
    assert b"caches" in resp.content


def test_static_asset_serves_icon():
    resp = server.static_asset(rf.get("/static/icon-192.png"), name="icon-192.png")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/png"
    assert resp.content[:4] == b"\x89PNG"


def test_static_asset_blocks_traversal():
    resp = server.static_asset(rf.get("/static/x"), name="..%2fconfig.yaml")
    assert resp.status_code == 404
    resp2 = server.static_asset(rf.get("/static/x"), name="nope.png")
    assert resp2.status_code == 404


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
    for k in ("cpu", "ram", "net_kbps", "ram_used_mb", "ram_total_mb",
              "ram_used_gb", "ram_total_gb", "dl_active", "dl_avg_s", "dl_done", "dl_total"):
        assert k in data


def test_index_shows_allocation_panel(monkeypatch):
    monkeypatch.setattr(server, "pick_model", lambda: "llama3.2")
    body = server.index(rf.get("/")).content.decode()
    assert "Allocation" in body
    assert "Workers / threads" in body
    assert "Avg speed / paper" in body
    assert "RAM used (live)" in body
    # placeholders must be substituted (no leftover template tokens)
    assert "{{" not in body


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


def test_suggest_returns_templates():
    data = json.loads(server.suggest(rf.get("/suggest")).content)
    assert isinstance(data["suggestions"], list) and len(data["suggestions"]) >= 5
    assert any("main findings" in s for s in data["suggestions"])


def test_suggest_is_topic_and_corpus_aware():
    server.CORPUS["topic"] = "malaria"
    server.CORPUS["df"] = pd.DataFrame([{"title": "t", "theme": "Vector control"}])
    data = json.loads(server.suggest(rf.get("/suggest")).content)
    joined = " ".join(data["suggestions"])
    assert "malaria" in joined
    assert "Vector control" in joined


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
