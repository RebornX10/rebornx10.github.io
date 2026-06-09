# Web API

The app exposes a handful of HTTP endpoints (defined in `app/server.py`). They back the web UI but can be called directly. State is in-memory and single-process: a built corpus lives in `CORPUS` until the next build or a restart, and identical builds are served from an on-disk cache (so the same `topic|dates|n` returns instantly). The most recently cached corpus is reloaded on startup.

Base URL examples: `http://localhost:8000` (global), `https://samdnx-sci-paper-rag.hf.space` (the demo Space).

---

## `GET /`
Returns the HTML UI. Template placeholders are filled server-side: the detected Ollama model, the effective max-papers cap (for the input's `max`), the Allocation-panel figures (download workers, CPU threads, RAM allocated), and a banner if no model is installed.

---

## `POST /build`
Start a corpus build. Runs asynchronously in a background thread and returns immediately.

**Request body (JSON):**
```json
{
  "topic": "graphene",
  "n": 25,
  "date_from": "2023-01-01",
  "date_to": "2025-12-31"
}
```
- `topic` (required) — free-text query.
- `n` — number of papers; clamped to `1..max_papers_cap`.
- `date_from` / `date_to` — optional; become OpenAlex `from_publication_date` / `to_publication_date` filters (applied by OpenAlex only; the other sources ignore them).
- `source` — `openalex` (default), `arxiv`, `pubmed` (PubMed Central open-access subset), or `crossref`. Unknown values fall back to `openalex`. arXiv/PubMed/Crossref keep only items that expose an open PDF.

**Response:** `{"job_id": "<hex>"}` (or `400` if `topic` is missing).

---

## `GET /status?job=<job_id>`
A build's current progress. The UI normally receives this over the `/events` SSE stream and only polls `/status` as a fallback.

**Response:**
```json
{ "stage": "Downloaded 12/25: …", "progress": 55, "done": false, "error": false }
```
- `progress` — 0–100.
- `stage` — human-readable status.
- `done` — true when finished (success or error).
- `error` — true if the build failed, was cancelled, or no papers matched.
- `cached` — present/true when the result was served from the on-disk cache.
- `suggested_n` — present when the RAM guard tripped (a smaller paper count to retry).

`400` if the job id is unknown.

---

## `POST /cancel`
Cancel a running build. Body: `{"job": "<job_id>"}`. Sets a flag the build loop honours; it stops fetching/downloading and keeps whatever was already downloaded. `400` if the job id is unknown.

---

## `POST /ask`
Ask a question about the current corpus (non-streaming; used as a fallback).

**Request body (JSON):** `{"question": "What improves stability?"}`

**Response:**
```json
{
  "answer": "…grounded answer…",
  "sources": [{"title": "...", "authors": ["..."], "journal": "...", "date": "...", "snippet": "..."}],
  "model": "llama3.2"
}
```

**Errors:**
- `400` `{"error": "Download a topic first."}` — no corpus in memory.
- `400` `{"error": "No Ollama model installed."}` — `pick_model()` found nothing.
- `500` `{"error": "Ollama error: …"}` — the model call failed.

Retrieval uses BM25 over the full paper text (title + abstract + content), cached per corpus; each source excerpt is the most query-relevant passage.

---

## `POST /ask_stream`
Same inputs as `/ask`, but streams the answer as it is generated. This is what the UI uses.

**Response:** `text/event-stream` (Server-Sent Events). Events are `data:`-prefixed JSON, one per `\n\n`:
- `{"sources": [...], "model": "..."}` — sent first.
- `{"delta": "token"}` — repeated as the model emits text.
- `{"done": true}` — at the end.
- `{"error": "..."}` — if the model call fails mid-stream.

Validation failures (no corpus / no model / missing question) return a normal JSON error with a `4xx` status instead of a stream.

---

## `GET /corpus?limit=300`
Summary + a page of the current corpus, for the browse panel.

**Response:** `{"topic", "count", "with_text", "shown", "papers": [{"title","authors","journal","date","country","abstract","has_text","doi","pdf_url"}]}`. `{"count": 0, "papers": []}` when nothing is loaded.

## `GET /corpora` · `POST /corpus/select`
Multi-corpus switcher. `GET /corpora` lists previously built corpora from the cache: `{"current": "<key>", "items": [{"key","topic","count","created"}]}`. `POST /corpus/select {"key": "..."}` makes one of them the active corpus (from an in-memory LRU or the on-disk cache); `404` if the key is unknown.

## `GET /download/csv` · `/download/parquet` · `/download/bibtex` · `/download/ris`
Download the current corpus as a file (`Content-Disposition: attachment`, topic-slugged filename): CSV, Parquet, BibTeX (`.bib`), or RIS (`.ris`, for Zotero/EndNote). `404` if no corpus is loaded.

## `GET /suggest`
Question-bar completions: generic templates plus topic- and corpus-aware questions. `{"suggestions": ["..."]}`.

## `GET /metrics`
Live system metrics: `cpu`, `ram`, `net_kbps`, `ram_used_gb`/`ram_total_gb`, and download stats `dl_active`/`dl_avg_s`/`dl_done`/`dl_total`. Used as the polling fallback.

## `GET /stats`
Cumulative observability counters: `uptime_s`, `builds`, `papers`, `with_text`, `questions`, `last_build_s`, `avg_retrieval_ms`, `avg_answer_ms`.

## `GET /events?job=<id>`
Server-Sent-Events push that the UI uses instead of polling: each ~1s tick is `data: {"metrics": {…}, "stats": {…}}` (the `stats` block is the same shape as `/stats`, feeding the in-UI Session-stats dashboard), and if `job` is given, also `"status": {…}` (the same shape as `/status`). The stream ends when the job finishes. The client falls back to polling `/metrics` (1s) + `/stats` (5s) + `/status` if EventSource never connects.

## PWA endpoints
`GET /manifest.webmanifest`, `GET /sw.js` (root-scoped service worker, version auto-busted by an asset hash), `GET /static/<icon>.png`, `GET /favicon.ico`.

---

## Example: scripted build + ask

```bash
BASE=http://localhost:8000
JOB=$(curl -s -X POST $BASE/build -H 'Content-Type: application/json' \
      -d '{"topic":"graphene","n":5,"date_from":"2023-01-01"}' \
      | python -c "import sys,json;print(json.load(sys.stdin)['job_id'])")

# poll until done
until curl -s "$BASE/status?job=$JOB" | grep -q '"done": true'; do sleep 2; done

curl -s -X POST $BASE/ask -H 'Content-Type: application/json' \
     -d '{"question":"What is graphene used for?"}'
```

> On a CPU-only deployment (e.g. the free HF Space), the first `/ask` can take 30–60s while the model loads and runs.
