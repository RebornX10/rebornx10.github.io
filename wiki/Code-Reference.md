# Code Reference

Every module and public function in the `app/` package, plus the entry points. Signatures match the source; defaults that read from config are shown as the config key.

---

## `app/config.py`
Loads `config.yaml` and applies environment-variable overrides.

- **`load(path=None) -> dict`** — read the YAML file (default `config.yaml`, or `$CONFIG_FILE`) and apply the `_ENV_OVERRIDES`. Returns the merged config dict.
- **`_as_bool(v) -> bool`** — parse env strings (`1/true/yes/on` → `True`) for boolean settings.
- **`CONFIG`** — module-level dict, the result of `load()`, imported everywhere.
- **`_ENV_OVERRIDES`** — maps env var → `(("section","key"), cast)`. See [Configuration](Configuration#environment-variable-overrides).

---

## `app/http.py`
Shared HTTP client.

- **`SESSION`** — a `requests.Session` with a polite-pool User-Agent and an `HTTPAdapter` (`pool_connections=32, pool_maxsize=32`) so parallel downloads don't queue for connections. Safe to share across threads.
- **`BROWSER_UA`** — a Chrome-like User-Agent used only for fetching PDF bytes (gets past naive publisher bot blocks).

---

## `app/models.py`

- **`Paper`** — the dataclass that flows through the pipeline. Fields:
  `openalex_id, doi, title, authors[list], date, journal, country, countries[list], abstract, pdf_url, pdf_candidates[list], content, theme`.
  `content` is filled after download; `theme` defaults to the OpenAlex topic and may be overwritten by the LLM tagger.

---

## `app/openalex.py`
Metadata from OpenAlex.

- **`reconstruct_abstract(inv_index) -> str | None`** — OpenAlex stores abstracts as an inverted index `{word: [positions]}`; this rebuilds the readable text. Returns `None` for empty/missing input.
- **`parse_work(w: dict) -> Paper`** — convert one OpenAlex "work" into a `Paper`: collects authors + institution countries, the journal, date, DOI, reconstructed abstract, the primary topic (as `theme`), and a **ranked, de-duplicated list of OA PDF URLs** (repository copies first, publisher copies last).
- **`fetch_metadata(n=100, *, search=None, extra_filters=None, require_pdf=True) -> Iterator[Paper]`** — yield up to `n` open-access papers. Always filters `is_oa:true` (+ `has_fulltext:true` when `require_pdf`), adds any `extra_filters`, paginates with a cursor, and (when `require_pdf`) skips papers with no PDF URL.

---

## `app/download.py`
Download OA PDFs and extract text. `_DL = CONFIG["download"]`.

- **`_fetch_pdf_bytes(url, deadline) -> bytes | None`** — stream a PDF with `(connect_timeout, read_timeout)`. Bails early if the response isn't a PDF, exceeds `max_pdf_bytes`, or passes `deadline` (a `time.monotonic()` value — guards against slow-but-steady servers a read timeout never catches).
- **`download_fulltext(paper, *, max_chars=…, deadline_s=…) -> Paper`** — try the paper's ranked candidate URLs within a per-paper wall-clock budget; on the first that yields a parseable PDF, set `paper.content` (truncated to `max_chars`) and record the working `pdf_url`. Never raises — failures are logged and the paper is returned unchanged.
- **`download_many(papers, *, workers=…, progress=None) -> list[Paper]`** — download many papers concurrently with a `ThreadPoolExecutor`. `progress(done, total, paper)` is called once per finished paper **in the calling thread**, so it's safe to update shared UI/job state from it.

---

## `app/theme.py`
Optional LLM theme tagging.

- **`SYSTEM`** — the system prompt instructing the model to return a 1–4 word theme tag.
- **`tag_theme(paper, client) -> Paper`** — given an `anthropic.Anthropic` client, set `paper.theme` from the title + abstract (or content). Used only when `build_corpus(..., with_theme=True)`.

---

## `app/corpus.py`
End-to-end orchestration. `COLUMNS` defines the output column order.

- **`build_corpus(n=25, *, search=None, extra_filters=None, with_fulltext=True, with_theme=False, workers=…) -> DataFrame`** — fetch metadata, optionally download full text (in parallel), optionally LLM-tag themes, then return a DataFrame with the canonical columns. `with_theme=False` (default) keeps the free OpenAlex theme.
- **`save_corpus(df, out=None) -> None`** — write `<out>.parquet` and `<out>.csv` (default basename from config). Creates the parent directory if needed (so `OUTPUT_BASENAME=data/papers` works with a mounted volume).

---

## `app/ollama_client.py`
Global LLM access. `_OLLAMA = CONFIG["ollama"]`.

- **`list_models() -> list[str]`** — names of installed models via `/api/tags`; `[]` if Ollama is unreachable.
- **`pick_model() -> str | None`** — `OLLAMA_MODEL`/config value if set, else the first installed model, else `None`.
- **`chat(question, context, model) -> str`** — send a grounded prompt (system instructions + paper excerpts + question) to `/api/chat` and return the answer text.

---

## `app/retrieval.py`
Lightweight RAG. `_R = CONFIG["retrieval"]`.

- **`_text(v) -> str`** / **`_authors(v) -> list`** — coerce possibly-`NaN`/numpy values from a DataFrame into clean `str`/`list` (avoids crashes on reloaded Parquet).
- **`build_context(df, question, k=None, budget=None) -> (context_str, sources)`** — score papers by keyword overlap of the question against title+abstract, take the top `k`, and assemble up to `budget` characters of excerpts. Returns the context string and a list of `{title, journal, date}` source dicts.

---

## `app/server.py`
The Django application. State: `JOBS` (job_id → progress dict), `CORPUS` (current DataFrame), `_LOCK`.

- **`run_build(job_id, topic, date_from, date_to, n) -> None`** — background worker: builds OpenAlex filters from the dates, fetches metadata, runs `download_many` with a progress callback that updates the job, assembles the DataFrame into `CORPUS`, and saves to disk. Updates the job's `stage`/`progress`/`done`/`error`.
- **`index(request)`** — render the UI, substituting `{{MODEL}}`, `{{MAX_PAPERS}}`, `{{BANNER}}`.
- **`build(request)`** — `POST`; validate topic, clamp `n` to `max_papers_cap`, start the background thread, return `{job_id}`.
- **`status(request)`** — `GET ?job=…`; return the job's progress dict.
- **`ask(request)`** — `POST`; require a built corpus + a model, build context, call `chat`, return `{answer, sources, model}`.
- **`run() -> None`** — start Django's dev server on `host:port` (optionally opening a browser). Called by `main.py`.
- **`urlpatterns` / `application`** — route table and WSGI app.

See [Web API](Web-API) for request/response details.

---

## Entry points

- **`main.py`** — imports and calls `app.server.run()`.
- **`pipeline.py`** — back-compat shim re-exporting `build_corpus, save_corpus, fetch_metadata, download_fulltext, download_many, Paper` so notebooks can `import pipeline`.
