from __future__ import annotations

import html
import json
import sys
import threading
import uuid
import webbrowser
from dataclasses import asdict
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.urls import path

from app.config import CONFIG
from app.corpus import save_corpus
from app.download import download_many
from app.ollama_client import chat, pick_model
from app.openalex import fetch_metadata
from app.retrieval import build_context
from app.system import (
    _mem_limit_bytes, _mem_used_bytes, effective_max_papers, metrics, papers_for_target,
)

TEMPLATE = (Path(__file__).parent / "templates" / "index.html").read_text()

JOBS: dict[str, dict] = {}
CORPUS: dict[str, object] = {}
_LOCK = threading.Lock()


def run_build(job_id: str, topic: str, date_from: str, date_to: str, n: int) -> None:
    job = JOBS[job_id]
    dl = CONFIG["download"]
    guard = dl.get("ram_guard_pct", 85) / 100.0
    target = dl.get("ram_target_pct", 80)
    baseline = _mem_used_bytes()
    total_ram = _mem_limit_bytes()
    state = {"done": 0, "oom": False}
    try:
        filters = []
        if date_from:
            filters.append(f"from_publication_date:{date_from}")
        if date_to:
            filters.append(f"to_publication_date:{date_to}")
        extra = ",".join(filters) or None

        job.update(stage="Searching OpenAlex…", progress=4)
        papers = list(fetch_metadata(n, search=topic or None, extra_filters=extra))
        if not papers:
            job.update(stage="No open-access papers matched that query.",
                       progress=100, done=True, error=True)
            return

        total = len(papers)

        def on_progress(done, total, paper):
            state["done"] = done
            job.update(stage=f"Downloaded {done}/{total}: {(paper.title or '')[:55]}…",
                       progress=5 + int(90 * done / total))

        def stop(done):
            # Abort before an OOM: the save step roughly doubles the corpus text,
            # so project the eventual peak from the growth so far.
            grown = max(0, _mem_used_bytes() - baseline)
            if (baseline + grown * 2) / total_ram >= guard:
                state["oom"] = True
                return True
            return False

        download_many(papers, workers=dl["workers"], progress=on_progress, stop=stop)
        if state["oom"]:
            raise MemoryError

        job.update(stage="Assembling dataset…", progress=97)
        df = pd.DataFrame([asdict(p) for p in papers])
        with _LOCK:
            CORPUS["df"] = df
            CORPUS["topic"] = topic
        save_corpus(df)
        with_text = int(df["content"].notna().sum())
        job.update(stage=f"Done — {total} papers ({with_text} with full text).",
                   progress=100, done=True)
    except MemoryError:
        suggested = papers_for_target(max(1, state["done"]), baseline, target)
        at = f" at {state['done']} papers" if state["done"] else ""
        job.update(
            stage=f"⚠️ Ran low on memory{at}. Try about {suggested} papers to keep RAM ≤ {int(target)}%.",
            progress=100, done=True, error=True, suggested_n=suggested)
    except Exception as e:
        job.update(stage=f"Error: {e}", progress=100, done=True, error=True)


def index(request):
    model = pick_model()
    banner = "" if model else "No Ollama model found. Run `ollama pull llama3.2`, then reload."
    page = TEMPLATE.replace("{{MODEL}}", html.escape(model or "none"))
    page = page.replace("{{MAX_PAPERS}}", str(effective_max_papers()))
    return HttpResponse(page.replace("{{BANNER}}", html.escape(banner)))


def build(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    data = json.loads(request.body or "{}")
    topic = (data.get("topic") or "").strip()
    if not topic:
        return HttpResponseBadRequest("topic is required")
    n = max(1, min(int(data.get("n", CONFIG["openalex"]["max_papers"])),
                   effective_max_papers()))
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"stage": "Starting…", "progress": 0, "done": False, "error": False}
    threading.Thread(
        target=run_build,
        args=(job_id, topic, data.get("date_from", ""), data.get("date_to", ""), n),
        daemon=True,
    ).start()
    return JsonResponse({"job_id": job_id})


def status(request):
    job = JOBS.get(request.GET.get("job", ""))
    if job is None:
        return HttpResponseBadRequest("unknown job")
    return JsonResponse(job)


def ask(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    df = CORPUS.get("df")
    if df is None or len(df) == 0:
        return JsonResponse({"error": "Download a topic first."}, status=400)
    model = pick_model()
    if not model:
        return JsonResponse({"error": "No Ollama model installed."}, status=400)
    question = (json.loads(request.body or "{}").get("question") or "").strip()
    if not question:
        return HttpResponseBadRequest("question is required")
    context, sources = build_context(df, question)
    try:
        answer = chat(question, context, model)
    except Exception as e:
        return JsonResponse({"error": f"Ollama error: {e}"}, status=500)
    return JsonResponse({"answer": answer, "sources": sources, "model": model})


def metrics_view(request):
    return JsonResponse(metrics())


if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY="local-dev-only",
        ALLOWED_HOSTS=["*"],
        ROOT_URLCONF=__name__,
        MIDDLEWARE=["django.middleware.common.CommonMiddleware"],
    )

urlpatterns = [
    path("", index),
    path("build", build),
    path("status", status),
    path("ask", ask),
    path("metrics", metrics_view),
]

application = get_wsgi_application()


def run() -> None:
    from django.core.management import execute_from_command_line

    import os

    host = CONFIG["server"]["host"]
    port = CONFIG["server"]["port"]
    url = f"http://{host}:{port}"
    if CONFIG["server"]["open_browser"] and "RUN_MAIN" not in os.environ:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"\n  Local Paper Research Assistant → {url}\n")
    execute_from_command_line([sys.argv[0], "runserver", f"{host}:{port}", "--noreload"])
