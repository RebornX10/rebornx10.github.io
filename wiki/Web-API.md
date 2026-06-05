# Web API

The app exposes four HTTP endpoints (defined in `app/server.py`). They back the web UI but can be called directly. State is in-memory and single-process: a built corpus lives in `CORPUS` until the next build or a restart.

Base URL examples: `http://localhost:8000` (global), `https://samdnx-sci-paper-rag.hf.space` (the demo Space).

---

## `GET /`
Returns the HTML UI. Template placeholders are filled server-side: the detected Ollama model, the `max_papers_cap` (for the input's `max`), and a banner if no model is installed.

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
- `date_from` / `date_to` — optional; become OpenAlex `from_publication_date` / `to_publication_date` filters.

**Response:** `{"job_id": "<hex>"}` (or `400` if `topic` is missing).

---

## `GET /status?job=<job_id>`
Poll a build's progress. The UI calls this every 0.5s.

**Response:**
```json
{ "stage": "Downloaded 12/25: …", "progress": 55, "done": false, "error": false }
```
- `progress` — 0–100.
- `stage` — human-readable status.
- `done` — true when finished (success or error).
- `error` — true if the build failed or no papers matched.

`400` if the job id is unknown.

---

## `POST /ask`
Ask a question about the most recently built corpus.

**Request body (JSON):** `{"question": "What improves stability?"}`

**Response:**
```json
{
  "answer": "…grounded answer…",
  "sources": [{"title": "...", "journal": "...", "date": "..."}],
  "model": "llama3.2"
}
```

**Errors:**
- `400` `{"error": "Download a topic first."}` — no corpus in memory.
- `400` `{"error": "No Ollama model installed."}` — `pick_model()` found nothing.
- `500` `{"error": "Ollama error: …"}` — the model call failed.

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
