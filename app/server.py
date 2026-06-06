from __future__ import annotations

import html
import io
import json
import logging
import mimetypes
import os
import re
import sys
import threading
import time
import uuid
import webbrowser
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.http import (
    HttpResponse, HttpResponseBadRequest, HttpResponseNotFound, JsonResponse,
    StreamingHttpResponse,
)
from django.urls import path

from app.config import CONFIG
from app.corpus import (
    cache_key, list_cached, load_from_cache, load_with_topic, save_corpus, save_to_cache,
)
from app.arxiv import fetch_metadata as arxiv_fetch
from app.crossref import fetch_metadata as crossref_fetch
from app.pubmed import fetch_metadata as pubmed_fetch
from app.download import download_fulltext
from app.ollama_client import chat, chat_stream, pick_model, verify_claims, warm_model
from app.openalex import fetch_metadata

SOURCES = ("openalex", "arxiv", "pubmed", "crossref")
_FETCHERS = {"arxiv": arxiv_fetch, "pubmed": pubmed_fetch, "crossref": crossref_fetch}


def _fetcher(source):
    # openalex resolves to the module-global name so tests can monkeypatch it
    return _FETCHERS.get(source, fetch_metadata)
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
# Inject an asset-hash version so the service worker cache auto-busts whenever the
# HTML/CSS/JS/manifest change (otherwise clients keep serving stale shells).
_SW_VERSION = __import__("hashlib").sha1(
    (APP_CSS + APP_JS + TEMPLATE + MANIFEST).encode()).hexdigest()[:8]
SW_JS = (_STATIC / "sw.js").read_text().replace("__SWV__", _SW_VERSION)

JOBS: dict[str, dict] = {}
CORPUS: dict[str, object] = {}
_LOADED: "OrderedDict[str, object]" = OrderedDict()  # small in-memory LRU of recent corpora
_LRU_MAX = 3
_LOCK = threading.Lock()

# Live download stats for the System panel (polled via /metrics every second).
DL: dict[str, object] = {"active": False, "done": 0, "total": 0, "avg_s": 0.0, "t0": 0.0}

# Cumulative observability counters (exposed at /stats).
STATS: dict = {"started": time.time(), "builds": 0, "papers": 0, "with_text": 0,
               "questions": 0, "retrieval_ms": [], "answer_ms": [], "last_build_s": 0.0}


def _cap(lst: list, v, n: int = 100) -> None:
    lst.append(v)
    if len(lst) > n:
        del lst[:-n]


def _checkpoint(papers, out: str) -> None:
    """Write a partial parquet so an interrupted build isn't lost entirely."""
    try:
        pd.DataFrame([asdict(p) for p in papers]).to_parquet(f"{out}.partial.parquet")
    except Exception as e:
        log.warning("checkpoint write failed: %s", e)


def _warm_async() -> None:
    """Preload the LLM in the background (no-op if disabled) so the first answer
    after a build/startup doesn't pay a cold model load."""
    if CONFIG["ollama"].get("warm_on_start", True):
        threading.Thread(target=warm_model, daemon=True).start()


def _set_corpus(df, topic: str, key: str = "") -> None:
    with _LOCK:
        CORPUS["df"] = df
        CORPUS["topic"] = topic
        CORPUS["key"] = key
        if key:
            _LOADED[key] = df
            _LOADED.move_to_end(key)
            while len(_LOADED) > _LRU_MAX:
                _LOADED.popitem(last=False)


def run_build(job_id: str, topic: str, date_from: str, date_to: str, n: int,
              source: str = "openalex") -> None:
    job = JOBS[job_id]
    dl = CONFIG["download"]
    guard = dl.get("ram_guard_pct", 85) / 100.0
    target = dl.get("ram_target_pct", 80)
    baseline = _mem_used_bytes()
    total_ram = _mem_limit_bytes()
    workers = download_workers()
    state = {"done": 0, "oom": False, "cancelled": False}
    log.info("Build start: topic=%r n=%d | download workers=%d | baseline RAM=%.2f GB / %.2f GB | "
             "abort if projected peak > %.0f%%",
             topic, n, workers, baseline / 1e9, total_ram / 1e9, guard * 100)

    # Cache hit: identical request -> load instantly, no OpenAlex, no downloads.
    key = cache_key(topic, date_from, date_to, n, source)
    cached = load_from_cache(key)
    if cached is not None and not job.get("cancel"):
        _set_corpus(cached, topic, key)
        with_text = int(cached["content"].notna().sum()) if "content" in cached else 0
        log.info("Cache hit for %r: %d papers", topic, len(cached))
        job.update(stage=f"Loaded {len(cached)} papers from cache ({with_text} with full text).",
                   progress=100, done=True, cached=True)
        _warm_async()  # preload the model so the user's first question is fast
        return

    def ram_guard_tripped(done: int) -> bool:
        grown = max(0, _mem_used_bytes() - baseline)
        if (baseline + grown * 2) / total_ram >= guard:
            log.warning("RAM guard tripped at %d papers (projected peak >= %.0f%%)", done, guard * 100)
            state["oom"] = True
            return True
        return False

    try:
        filters = []
        if date_from:
            filters.append(f"from_publication_date:{date_from}")
        if date_to:
            filters.append(f"to_publication_date:{date_to}")
        extra = ",".join(filters) or None

        job.update(stage=f"Searching {source}…", progress=4)
        DL.update(active=True, done=0, total=n, avg_s=0.0, t0=time.monotonic())

        # Pipeline: submit each paper for download as its metadata page streams in,
        # so PDF fetches overlap the (sequential) source search.
        fetch = _fetcher(source)
        papers, futures = [], {}
        ex = ThreadPoolExecutor(max_workers=max(1, workers))
        try:
            for paper in fetch(n, search=topic or None, extra_filters=extra):
                if job.get("cancel"):
                    state["cancelled"] = True
                    break
                papers.append(paper)
                futures[ex.submit(download_fulltext, paper)] = paper
                job.update(stage=f"Found {len(papers)} papers… downloading in parallel", progress=5)

            total = len(papers)
            if total == 0 and not state["cancelled"]:
                job.update(stage="No open-access papers matched that query.",
                           progress=100, done=True, error=True)
                return

            if not state["cancelled"]:
                for fut in as_completed(futures):
                    if job.get("cancel"):
                        state["cancelled"] = True
                        break
                    state["done"] += 1
                    done = state["done"]
                    paper = futures[fut]
                    try:
                        fut.result()
                    except Exception as e:
                        log.warning("worker failed for %s: %s", paper.title, e)
                    elapsed = time.monotonic() - DL["t0"]
                    DL.update(active=True, done=done, total=total,
                              avg_s=(elapsed / done if done else 0.0))
                    job.update(stage=f"Downloaded {done}/{total}: {(paper.title or '')[:55]}…",
                               progress=5 + int(90 * done / total))
                    ckpt = dl.get("checkpoint_every", 0)
                    if ckpt and done % ckpt == 0:
                        _checkpoint(papers, dl["output_basename"])
                    if ram_guard_tripped(done):
                        break
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

        if state["oom"]:
            raise MemoryError
        if state["cancelled"]:
            log.info("Build cancelled at %d papers", state["done"])
            job.update(stage=f"Cancelled — kept {state['done']} downloaded papers.",
                       progress=100, done=True, error=True, cancelled=True)
            return

        job.update(stage="Assembling dataset…", progress=97)
        log.info("Assembling DataFrame from %d papers…", total)
        df = pd.DataFrame([asdict(p) for p in papers])
        _set_corpus(df, topic, key)
        save_corpus(df)
        save_to_cache(key, df, topic)
        try:
            os.remove(f"{dl['output_basename']}.partial.parquet")  # final write supersedes it
        except OSError:
            pass
        with_text = int(df["content"].notna().sum())
        STATS["builds"] += 1
        STATS["papers"] += total
        STATS["with_text"] += with_text
        STATS["last_build_s"] = round(time.monotonic() - DL["t0"], 1)
        log.info("Build done: %d papers, %d with full text, RAM now %.2f GB",
                 total, with_text, _mem_used_bytes() / 1e9)
        job.update(stage=f"Done — {total} papers ({with_text} with full text).",
                   progress=100, done=True)
        _warm_async()  # preload the model so the user's first question is fast
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
    source = (data.get("source") or "openalex").strip().lower()
    if source not in SOURCES:
        source = "openalex"
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"stage": "Starting…", "progress": 0, "done": False, "error": False,
                    "cancel": False}
    threading.Thread(
        target=run_build,
        args=(job_id, topic, data.get("date_from", ""), data.get("date_to", ""), n, source),
        daemon=True,
    ).start()
    return JsonResponse({"job_id": job_id})


def status(request):
    job = JOBS.get(request.GET.get("job", ""))
    if job is None:
        return HttpResponseBadRequest("unknown job")
    return JsonResponse(job)


def cancel(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    job = JOBS.get(json.loads(request.body or "{}").get("job", ""))
    if job is None:
        return HttpResponseBadRequest("unknown job")
    job["cancel"] = True
    return JsonResponse({"ok": True})


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


def _sse(obj) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def ask_stream(request):
    """Server-Sent-Events variant of /ask: streams the answer token-by-token.
    Validation failures return a normal JSON error; the happy path streams."""
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
    t_retr = time.monotonic()
    context, sources = build_context(df, question)
    retrieval_ms = round((time.monotonic() - t_retr) * 1000, 1)

    def gen():
        t_ans = time.monotonic()
        yield _sse({"sources": sources, "model": model})
        try:
            parts = []
            for tok in chat_stream(question, context, model):
                parts.append(tok)
                yield _sse({"delta": tok})
            if CONFIG["retrieval"].get("verify") and parts:
                try:
                    note = verify_claims("".join(parts), context, model)
                    if note:
                        yield _sse({"verify": note})
                except Exception as e:
                    log.warning("verification failed: %s", e)
            yield _sse({"done": True})
        except Exception as e:
            log.warning("ask_stream failed: %s", e)
            yield _sse({"error": f"Ollama error: {e}"})
        finally:
            STATS["questions"] += 1
            _cap(STATS["retrieval_ms"], retrieval_ms)
            _cap(STATS["answer_ms"], round((time.monotonic() - t_ans) * 1000, 1))

    resp = StreamingHttpResponse(gen(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"          # don't let a proxy buffer the stream
    resp["Content-Encoding"] = "identity"     # skip GZipMiddleware (it would buffer)
    return resp


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


def _s(v) -> str:
    return v if isinstance(v, str) else ""


def _alist(v) -> list:
    if isinstance(v, (list, tuple)):
        return list(v)
    if hasattr(v, "tolist"):
        return list(v.tolist())
    return []


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "corpus"


def corpus_view(request):
    """Summary + a page of papers for the browse panel (and for resuming)."""
    df = CORPUS.get("df")
    if df is None or len(df) == 0:
        return JsonResponse({"count": 0, "papers": []})
    limit = max(1, min(int(request.GET.get("limit", 300)), 1000))
    total = len(df)
    with_text = int(df["content"].notna().sum()) if "content" in df.columns else 0
    papers = []
    for r in df.head(limit).to_dict("records"):
        papers.append({
            "title": _s(r.get("title")) or "Untitled",
            "authors": [a for a in _alist(r.get("authors")) if isinstance(a, str)][:8],
            "journal": _s(r.get("journal")),
            "date": _s(r.get("date")),
            "country": _s(r.get("country")),
            "abstract": _s(r.get("abstract"))[:800],
            "has_text": bool(_s(r.get("content"))),
            "cited_by": int(r["cited_by_count"]) if pd.notna(r.get("cited_by_count")) else 0,
            "doi": _s(r.get("doi")),
            "pdf_url": _s(r.get("pdf_url")),
        })
    return JsonResponse({"topic": CORPUS.get("topic") or "", "key": CORPUS.get("key") or "",
                         "count": total, "with_text": with_text, "shown": len(papers),
                         "papers": papers})


def corpora_view(request):
    """List built corpora (from the cache) for the topic switcher."""
    return JsonResponse({"current": CORPUS.get("key") or "", "items": list_cached()})


def corpus_select(request):
    """Switch the active corpus to a previously built one (from the LRU or cache)."""
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    key = json.loads(request.body or "{}").get("key", "")
    df = _LOADED.get(key)
    topic = CORPUS.get("topic", "") if key == CORPUS.get("key") else ""
    if df is None:
        df, topic = load_with_topic(key)
    if df is None:
        return JsonResponse({"error": "unknown corpus"}, status=404)
    _set_corpus(df, topic, key)
    log.info("Switched corpus -> topic=%r (%d papers)", topic, len(df))
    return JsonResponse({"ok": True, "topic": topic, "count": int(len(df))})


def download_csv(request):
    df = CORPUS.get("df")
    if df is None or len(df) == 0:
        return HttpResponseNotFound("no corpus")
    resp = HttpResponse(df.to_csv(index=False), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="papers-{_slug(CORPUS.get("topic"))}.csv"'
    return resp


def download_parquet(request):
    df = CORPUS.get("df")
    if df is None or len(df) == 0:
        return HttpResponseNotFound("no corpus")
    buf = io.BytesIO()
    df.to_parquet(buf)
    resp = HttpResponse(buf.getvalue(), content_type="application/octet-stream")
    resp["Content-Disposition"] = f'attachment; filename="papers-{_slug(CORPUS.get("topic"))}.parquet"'
    return resp


def _year(d) -> str:
    d = _s(d)
    return d[:4] if len(d) >= 4 and d[:4].isdigit() else ""


def _doi(d) -> str:
    return _s(d).replace("https://doi.org/", "").replace("http://doi.org/", "")


def _to_bibtex(df) -> str:
    out = []
    for i, r in enumerate(df.to_dict("records")):
        authors = [a for a in _alist(r.get("authors")) if isinstance(a, str)]
        year = _year(r.get("date"))
        surname = authors[0].split()[-1] if authors else "anon"
        key = (re.sub(r"[^A-Za-z0-9]", "", f"{surname}{year}") or "ref") + str(i)
        fields = [f"  title = {{{_s(r.get('title'))}}}"]
        if authors:
            fields.append("  author = {" + " and ".join(authors) + "}")
        if _s(r.get("journal")):
            fields.append(f"  journal = {{{_s(r.get('journal'))}}}")
        if year:
            fields.append(f"  year = {{{year}}}")
        if _doi(r.get("doi")):
            fields.append(f"  doi = {{{_doi(r.get('doi'))}}}")
        out.append("@article{" + key + ",\n" + ",\n".join(fields) + "\n}")
    return "\n\n".join(out) + "\n"


def _to_ris(df) -> str:
    blocks = []
    for r in df.to_dict("records"):
        lines = ["TY  - JOUR", f"TI  - {_s(r.get('title'))}"]
        lines += [f"AU  - {a}" for a in _alist(r.get("authors")) if isinstance(a, str)]
        if _s(r.get("journal")):
            lines.append(f"JO  - {_s(r.get('journal'))}")
        if _year(r.get("date")):
            lines.append(f"PY  - {_year(r.get('date'))}")
        if _doi(r.get("doi")):
            lines.append(f"DO  - {_doi(r.get('doi'))}")
        lines.append("ER  - ")
        blocks.append("\n".join(lines))
    return "\n".join(blocks) + "\n"


def _citation_response(text: str, ext: str, ctype: str):
    resp = HttpResponse(text, content_type=ctype)
    resp["Content-Disposition"] = f'attachment; filename="papers-{_slug(CORPUS.get("topic"))}.{ext}"'
    return resp


def download_bibtex(request):
    df = CORPUS.get("df")
    if df is None or len(df) == 0:
        return HttpResponseNotFound("no corpus")
    return _citation_response(_to_bibtex(df), "bib", "application/x-bibtex")


def download_ris(request):
    df = CORPUS.get("df")
    if df is None or len(df) == 0:
        return HttpResponseNotFound("no corpus")
    return _citation_response(_to_ris(df), "ris", "application/x-research-info-systems")


def _metrics_payload() -> dict:
    m = metrics()
    m["ram_used_gb"] = round(m["ram_used_mb"] / 1024, 2)
    m["ram_total_gb"] = round(m["ram_total_mb"] / 1024, 2)
    m["dl_active"] = bool(DL["active"])
    m["dl_avg_s"] = round(float(DL["avg_s"]), 2)
    m["dl_done"] = int(DL["done"])
    m["dl_total"] = int(DL["total"])
    return m


def metrics_view(request):
    return JsonResponse(_metrics_payload())


def _stats_payload() -> dict:
    """Cumulative observability counters (builds, papers, timings)."""
    def avg(xs):
        return round(sum(xs) / len(xs), 1) if xs else 0.0
    return {
        "uptime_s": round(time.time() - STATS["started"]),
        "builds": STATS["builds"],
        "papers": STATS["papers"],
        "with_text": STATS["with_text"],
        "questions": STATS["questions"],
        "last_build_s": STATS["last_build_s"],
        "avg_retrieval_ms": avg(STATS["retrieval_ms"]),
        "avg_answer_ms": avg(STATS["answer_ms"]),
    }


def stats_view(request):
    return JsonResponse(_stats_payload())


def events(request):
    """SSE push of live metrics (~1s) plus the active build's status, so the UI
    doesn't poll. `?job=<id>` includes that job's status in each tick."""
    job_id = request.GET.get("job", "")

    def gen():
        while True:
            payload = {"metrics": _metrics_payload(), "stats": _stats_payload()}
            job = JOBS.get(job_id)
            if job is not None:
                payload["status"] = job
            yield _sse(payload)
            if job is not None and job.get("done"):
                break          # build finished -> client reconnects metrics-only
            time.sleep(1)

    resp = StreamingHttpResponse(gen(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    resp["Content-Encoding"] = "identity"
    return resp


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
        MIDDLEWARE=[
            "django.middleware.gzip.GZipMiddleware",  # compress HTML/CSS/JS/JSON
            "django.middleware.common.CommonMiddleware",
        ],
    )

urlpatterns = [
    path("", index),
    path("build", build),
    path("status", status),
    path("cancel", cancel),
    path("ask", ask),
    path("ask_stream", ask_stream),
    path("suggest", suggest),
    path("corpus", corpus_view),
    path("corpora", corpora_view),
    path("corpus/select", corpus_select),
    path("download/csv", download_csv),
    path("download/parquet", download_parquet),
    path("download/bibtex", download_bibtex),
    path("download/ris", download_ris),
    path("metrics", metrics_view),
    path("stats", stats_view),
    path("events", events),
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
    if CORPUS.get("df") is None:  # resume the most recent corpus after a restart
        items = list_cached()
        if items:
            df, topic = load_with_topic(items[0]["key"])
            if df is not None:
                _set_corpus(df, topic, items[0]["key"])
                log.info("Resumed last corpus: topic=%r, %d papers", topic, len(df))
    log.info("Ollama: url=%s, model=%s", CONFIG["ollama"]["url"], pick_model() or "(none installed)")
    log.info("OpenAlex: mailto=%s, per_page=%d", CONFIG["openalex"]["mailto"], CONFIG["openalex"]["per_page"])
    _warm_async()  # start loading the model now so the first question is fast
    log.info("Serving on %s", url)

    if CONFIG["server"]["open_browser"] and "RUN_MAIN" not in os.environ:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    execute_from_command_line([sys.argv[0], "runserver", f"{host}:{port}", "--noreload"])
