import json
import time

import pandas as pd
import pytest
from django.test import RequestFactory

from app import server
from app.models import Paper

rf = RequestFactory()


@pytest.fixture(autouse=True)
def clear_state(monkeypatch):
    server.JOBS.clear()
    server.CORPUS.clear()
    server._LOADED.clear()
    # keep build tests hermetic: no corpus-cache reads/writes to disk
    monkeypatch.setattr(server, "load_from_cache", lambda key: None)
    monkeypatch.setattr(server, "save_to_cache", lambda *a, **k: None)
    yield
    server.JOBS.clear()
    server.CORPUS.clear()
    server._LOADED.clear()


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
    assert b"__SWV__" not in resp.content  # version placeholder must be substituted


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
    monkeypatch.setattr(server, "download_fulltext", lambda p, **k: p)
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


def test_events_streams_metrics_and_status():
    server.JOBS["e1"] = {"stage": "done", "progress": 100, "done": True, "error": False}
    resp = server.events(rf.get("/events?job=e1"))
    assert resp["Content-Type"] == "text/event-stream"
    body = b"".join(resp.streaming_content).decode()  # job is done -> gen ends after one tick
    assert '"metrics"' in body and '"status"' in body and '"done": true' in body


def test_events_first_tick_has_metrics():
    resp = server.events(rf.get("/events"))   # no job -> would loop; only read first tick
    assert resp["Content-Type"] == "text/event-stream"
    first = next(iter(resp.streaming_content)).decode()
    assert '"metrics"' in first


def test_corpus_endpoint_empty():
    server.CORPUS.clear()
    data = json.loads(server.corpus_view(rf.get("/corpus")).content)
    assert data["count"] == 0 and data["papers"] == []


def test_corpus_endpoint_lists_papers():
    server.CORPUS["topic"] = "graphene"
    server.CORPUS["df"] = pd.DataFrame([
        {"title": "Graphene", "authors": ["Ada", "Alan"], "journal": "Nature", "date": "2023",
         "country": "GB", "abstract": "about graphene", "content": "full text", "doi": "10.1/x",
         "pdf_url": "http://x/a.pdf", "cited_by_count": 99},
        {"title": "Other", "authors": ["Bob"], "journal": "J", "date": "2022",
         "country": "US", "abstract": "x", "content": None, "doi": None, "pdf_url": None,
         "cited_by_count": None}])
    data = json.loads(server.corpus_view(rf.get("/corpus")).content)
    assert data["count"] == 2 and data["with_text"] == 1 and data["topic"] == "graphene"
    assert data["papers"][0]["title"] == "Graphene"
    assert data["papers"][0]["has_text"] is True and data["papers"][1]["has_text"] is False
    assert data["papers"][0]["authors"] == ["Ada", "Alan"]
    assert data["papers"][0]["cited_by"] == 99 and data["papers"][1]["cited_by"] == 0


def test_download_csv_and_parquet():
    server.CORPUS["topic"] = "graphene"
    server.CORPUS["df"] = pd.DataFrame([{"title": "T", "content": "c"}])
    csv = server.download_csv(rf.get("/download/csv"))
    assert csv.status_code == 200 and csv["Content-Type"] == "text/csv"
    assert "attachment" in csv["Content-Disposition"] and ".csv" in csv["Content-Disposition"]
    assert b"title" in csv.content
    pq = server.download_parquet(rf.get("/download/parquet"))
    assert pq.status_code == 200 and pq.content[:4] == b"PAR1"


def test_download_without_corpus():
    server.CORPUS.clear()
    assert server.download_csv(rf.get("/download/csv")).status_code == 404
    assert server.download_parquet(rf.get("/download/parquet")).status_code == 404


def test_corpora_lists_current(monkeypatch):
    monkeypatch.setattr(server, "list_cached", lambda: [
        {"key": "k1", "topic": "alpha", "count": 1, "created": 2.0},
        {"key": "k2", "topic": "beta", "count": 1, "created": 1.0}])
    server._set_corpus(pd.DataFrame([{"title": "A", "content": "a"}]), "alpha", "k1")
    data = json.loads(server.corpora_view(rf.get("/corpora")).content)
    assert data["current"] == "k1"
    assert [i["key"] for i in data["items"]] == ["k1", "k2"]


def test_corpus_select_switches(monkeypatch):
    dfB = pd.DataFrame([{"title": "B", "content": "b"}])
    server._set_corpus(pd.DataFrame([{"title": "A", "content": "a"}]), "alpha", "k1")
    monkeypatch.setattr(server, "load_with_topic",
                        lambda key: (dfB, "beta") if key == "k2" else (None, ""))
    resp = server.corpus_select(rf.post("/corpus/select", data=json.dumps({"key": "k2"}),
                                        content_type="application/json"))
    assert resp.status_code == 200
    assert server.CORPUS["topic"] == "beta" and server.CORPUS["key"] == "k2"


def test_corpus_select_unknown(monkeypatch):
    monkeypatch.setattr(server, "load_with_topic", lambda key: (None, ""))
    resp = server.corpus_select(rf.post("/corpus/select", data=json.dumps({"key": "nope"}),
                                        content_type="application/json"))
    assert resp.status_code == 404


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
    monkeypatch.setattr(server, "download_fulltext", lambda p, **k: p)
    # force the RAM guard to trip (report memory as ~99% full)
    total = server._mem_limit_bytes()
    monkeypatch.setattr(server, "_mem_used_bytes", lambda: int(total * 0.99))
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


def test_cancel_sets_flag():
    server.JOBS["j1"] = {"stage": "x", "progress": 10, "done": False, "error": False, "cancel": False}
    resp = server.cancel(rf.post("/cancel", data=json.dumps({"job": "j1"}),
                                 content_type="application/json"))
    assert resp.status_code == 200
    assert server.JOBS["j1"]["cancel"] is True


def test_cancel_unknown_job():
    resp = server.cancel(rf.post("/cancel", data=json.dumps({"job": "nope"}),
                                 content_type="application/json"))
    assert resp.status_code == 400


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


def test_ask_stream_streams_tokens(monkeypatch):
    server.CORPUS["df"] = pd.DataFrame([
        {"title": "Graphene", "abstract": "graphene", "content": "graphene text",
         "authors": ["A"], "journal": "J", "date": "2023"}])
    monkeypatch.setattr(server, "pick_model", lambda: "llama3.2")
    monkeypatch.setattr(server, "chat_stream", lambda q, c, m: iter(["Hello ", "world"]))
    resp = server.ask_stream(rf.post("/ask_stream", data=json.dumps({"question": "what is graphene"}),
                                     content_type="application/json"))
    assert resp["Content-Type"] == "text/event-stream"
    body = b"".join(resp.streaming_content).decode()
    assert '"sources"' in body
    assert '"delta": "Hello "' in body and '"delta": "world"' in body
    assert '"done": true' in body


def test_ask_stream_emits_verification(monkeypatch):
    server.CORPUS["df"] = pd.DataFrame([
        {"title": "T", "abstract": "a", "content": "c", "authors": ["A"], "journal": "J", "date": "2023"}])
    monkeypatch.setattr(server, "pick_model", lambda: "m")
    monkeypatch.setattr(server, "chat_stream", lambda q, c, m: iter(["hello"]))
    monkeypatch.setattr(server, "verify_claims", lambda a, c, m: "All claims supported.")
    monkeypatch.setitem(server.CONFIG["retrieval"], "verify", True)
    resp = server.ask_stream(rf.post("/ask_stream", data=json.dumps({"question": "q"}),
                                     content_type="application/json"))
    body = b"".join(resp.streaming_content).decode()
    assert '"verify"' in body and "All claims supported" in body


def test_ask_stream_without_corpus():
    server.CORPUS.clear()
    resp = server.ask_stream(rf.post("/ask_stream", data=json.dumps({"question": "q"}),
                                     content_type="application/json"))
    assert resp.status_code == 400


def test_ask_stream_surfaces_model_error(monkeypatch):
    server.CORPUS["df"] = pd.DataFrame([
        {"title": "T", "abstract": "a", "content": "c", "authors": ["A"], "journal": "J", "date": "2023"}])
    monkeypatch.setattr(server, "pick_model", lambda: "m")

    def boom(*a, **k):
        raise RuntimeError("ollama down")
        yield  # pragma: no cover

    monkeypatch.setattr(server, "chat_stream", boom)
    resp = server.ask_stream(rf.post("/ask_stream", data=json.dumps({"question": "q"}),
                                     content_type="application/json"))
    body = b"".join(resp.streaming_content).decode()
    assert '"error"' in body and "ollama down" in body


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
