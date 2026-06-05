from __future__ import annotations

import html
import json
import logging
import mimetypes
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import asdict
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.http import (
    HttpResponse, HttpResponseBadRequest, HttpResponseNotFound, JsonResponse,
)
from django.urls import path

from app.config import CONFIG
from app.corpus import save_corpus
from app.download import download_many
from app.ollama_client import chat, pick_model
from app.openalex import fetch_metadata
from app.retrieval import build_context
from app.system import (
    _mem_limit_bytes, _mem_used_bytes, available_cpus, download_workers, effective_max_papers,
    log_resources, metrics, papers_for_target,
)

log = logging.getLogger("server")

TEMPLATE = (Path(__file__).parent / "templates" / "index.html").read_text()
_STATIC = Path(__file__).parent / "static"
APP_CSS = (_STATIC / "styles.css").read_text()
APP_JS = (_STATIC / "app.js").read_text()
MANIFEST = (_STATIC / "manifest.webmanifest").read_text()
SW_JS = (_STATIC / "sw.js").read_text()

JOBS: dict[str, dict] = {}
CORPUS: dict[str, object] = {}
_LOCK = threading.Lock()

# Live download stats for the System panel (polled via /metrics every second).
DL: dict[str, object] = {"active": False, "done": 0, "total": 0, "avg_s": 0.0, "t0": 0.0}


def run_build(job_id: str, topic: str, date_from: str, date_to: str, n: int) -> None:
    job = JOBS[job_id]
    dl = CONFIG["download"]
    guard = dl.get("ram_guard_pct", 85) / 100.0
    target = dl.get("ram_target_pct", 80)
    baseline = _mem_used_bytes()
    total_ram = _mem_limit_bytes()
    state = {"done": 0, "oom": False}
    log.info("Build start: topic=%r n=%d | download workers=%d | baseline RAM=%.2f GB / %.2f GB | "
             "abort if projected peak > %.0f%%",
             topic, n, download_workers(), baseline / 1e9, total_ram / 1e9, guard * 100)
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
        DL.update(active=True, done=0, total=total, avg_s=0.0, t0=time.monotonic())

        def on_progress(done, total, paper):
            state["done"] = done
            elapsed = time.monotonic() - DL["t0"]
            DL.update(active=True, done=done, total=total,
                      avg_s=(elapsed / done if done else 0.0))
            job.update(stage=f"Downloaded {done}/{total}: {(paper.title or '')[:55]}…",
                       progress=5 + int(90 * done / total))

        def stop(done):
            # Abort before an OOM: the save step roughly doubles the corpus text,
            # so project the eventual peak from the growth so far.
            grown = max(0, _mem_used_bytes() - baseline)
            projected = (baseline + grown * 2) / total_ram
            if projected >= guard:
                log.warning("RAM guard tripped at %d papers: projected peak %.0f%% >= %.0f%%",
                            done, projected * 100, guard * 100)
                state["oom"] = True
                return True
            return False

        download_many(papers, workers=download_workers(), progress=on_progress, stop=stop)
        if state["oom"]:
            raise MemoryError

        job.update(stage="Assembling dataset…", progress=97)
        log.info("Assembling DataFrame from %d papers…", total)
        df = pd.DataFrame([asdict(p) for p in papers])
        with _LOCK:
            CORPUS["df"] = df
            CORPUS["topic"] = topic
        save_corpus(df)
        with_text = int(df["content"].notna().sum())
        log.info("Build done: %d papers, %d with full text, RAM now %.2f GB",
                 total, with_text, _mem_used_bytes() / 1e9)
        job.update(stage=f"Done — {total} papers ({with_text} with full text).",
                   progress=100, done=True)
    except MemoryError:
        suggested = papers_for_target(max(1, state["done"]), baseline, target)
        at = f" at {state['done']} papers" if state["done"] else ""
        log.warning("OOM-guard: suggesting %d papers (target %.0f%% RAM)", suggested, target)
        job.update(
            stage=f"⚠️ Ran low on memory{at}. Try about {suggested} papers to keep RAM ≤ {int(target)}%.",
            progress=100, done=True, error=True, suggested_n=suggested)
    except Exception as e:
        log.exception("Build failed")
        job.update(stage=f"Error: {e}", progress=100, done=True, error=True)
    finally:
        DL["active"] = False  # keep last avg_s/done for display, just stop the clock


def index(request):
    model = pick_model()
    banner = "" if model else "No Ollama model found. Run `ollama pull llama3.2`, then reload."
    cap = effective_max_papers()
    ram_alloc = _mem_limit_bytes() * CONFIG["download"].get("ram_fraction", 0.85) / 1e9
    page = TEMPLATE.replace("{{MODEL}}", html.escape(model or "none"))
    page = page.replace("{{MAX_PAPERS_FMT}}", f"{cap:,}")
    page = page.replace("{{MAX_PAPERS}}", str(cap))
    page = page.replace("{{WORKERS}}", str(download_workers()))
    page = page.replace("{{CPU_THREADS}}", str(available_cpus()))
    page = page.replace("{{RAM_ALLOC}}", f"{ram_alloc:.1f}")
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


_QUESTION_TEMPLATES = [
    "What are the main findings?",
    "Summarize the key results.",
    "What methods were used?",
    "What are the limitations of these studies?",
    "What future work is suggested?",
    "What datasets or samples were used?",
    "How do the papers compare or disagree?",
    "What are the practical applications?",
]


def suggest(request):
    """Auto-complete suggestions for the question bar: generic templates plus
    topic- and corpus-aware questions seeded from the current download."""
    out = list(_QUESTION_TEMPLATES)
    topic = (CORPUS.get("topic") or "").strip()
    if topic:
        out += [f"What is the current consensus on {topic}?",
                f"What are the main challenges in {topic}?",
                f"What are the recent advances in {topic}?"]
    df = CORPUS.get("df")
    if df is not None and "theme" in getattr(df, "columns", []):
        themes = [t for t in df["theme"].dropna().unique().tolist()
                  if isinstance(t, str) and t][:6]
        out += [f"What do the papers say about {t}?" for t in themes]
    seen, deduped = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return JsonResponse({"suggestions": deduped})


def metrics_view(request):
    m = metrics()
    m["ram_used_gb"] = round(m["ram_used_mb"] / 1024, 2)
    m["ram_total_gb"] = round(m["ram_total_mb"] / 1024, 2)
    m["dl_active"] = bool(DL["active"])
    m["dl_avg_s"] = round(float(DL["avg_s"]), 2)
    m["dl_done"] = int(DL["done"])
    m["dl_total"] = int(DL["total"])
    return JsonResponse(m)


def app_css(request):
    return HttpResponse(APP_CSS, content_type="text/css")


def app_js(request):
    return HttpResponse(APP_JS, content_type="application/javascript")


def manifest_view(request):
    return HttpResponse(MANIFEST, content_type="application/manifest+json")


def sw_js(request):
    # Served from the root so its scope covers the whole app.
    resp = HttpResponse(SW_JS, content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/"
    resp["Cache-Control"] = "no-cache"
    return resp


def static_asset(request, name):
    """Serve binary static assets (PWA icons, favicon) from app/static."""
    p = _STATIC / name
    if "/" in name or ".." in name or not p.is_file():
        return HttpResponseNotFound("not found")
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    resp = HttpResponse(p.read_bytes(), content_type=ctype)
    resp["Cache-Control"] = "public, max-age=86400"
    return resp


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
    path("suggest", suggest),
    path("metrics", metrics_view),
    path("static/styles.css", app_css),
    path("static/app.js", app_js),
    path("manifest.webmanifest", manifest_view),
    path("sw.js", sw_js),
    path("favicon.ico", static_asset, {"name": "favicon.png"}),
    path("static/<str:name>", static_asset),
]

application = get_wsgi_application()


def _setup_logging(level_name: str) -> None:
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    # quiet the noisy libraries / per-request server log (metrics polls every 1s)
    for noisy in ("urllib3", "requests", "django.server", "django.request", "django"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def run() -> None:
    import os

    from django.core.management import execute_from_command_line

    _setup_logging(CONFIG["server"].get("log_level", "INFO"))
    host = CONFIG["server"]["host"]
    port = CONFIG["server"]["port"]
    url = f"http://{host}:{port}"

    log.info("=== Global Paper Research Assistant — starting ===")
    log_resources()
    log.info("Ollama: url=%s, model=%s", CONFIG["ollama"]["url"], pick_model() or "(none installed)")
    log.info("OpenAlex: mailto=%s, per_page=%d", CONFIG["openalex"]["mailto"], CONFIG["openalex"]["per_page"])
    log.info("Serving on %s", url)

    if CONFIG["server"]["open_browser"] and "RUN_MAIN" not in os.environ:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    execute_from_command_line([sys.argv[0], "runserver", f"{host}:{port}", "--noreload"])
