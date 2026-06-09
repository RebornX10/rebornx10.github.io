# Code Reference

Every module and the main public functions in the `app/` package, plus the entry points. Signatures match the source; defaults that read from config are shown as the config key. For end-to-end flow see [Architecture](Architecture-and-Data-Sources); for HTTP details see [Web API](Web-API).

---

## `app/config.py`
Loads `config.yaml` and applies environment-variable overrides.

- **`load(path=None) -> dict`** — read the YAML file (default `config.yaml`, or `$CONFIG_FILE`) and apply `_ENV_OVERRIDES`. Returns the merged config dict.
- **`_as_bool(v) -> bool`** — parse env strings (`1/true/yes/on` → `True`) for boolean settings.
- **`CONFIG`** — module-level dict, the result of `load()`, imported everywhere.
- **`_ENV_OVERRIDES`** — maps env var → `(("section","key"), cast)`. See [Configuration](Configuration#environment-variable-overrides).

---

## `app/http.py`
Shared HTTP client, reused by every source adapter and the downloader.

- **`SESSION`** — a `requests.Session` with a polite-pool User-Agent and a large connection pool (sized from `io_workers_cap`) so parallel downloads reuse keep-alive connections instead of churning sockets. Thread-safe.
- **`BROWSER_UA`** — a Chrome-like User-Agent used only for fetching PDF bytes (gets past naive publisher bot blocks).

---

## `app/models.py`

- **`Paper`** — the dataclass that flows through the pipeline. Fields:
  `openalex_id, doi, title, authors[list], date, journal, country, countries[list], abstract, pdf_url, pdf_candidates[list], content, theme, cited_by_count`.
  `content` is filled after download; `theme` defaults to the source's topic and may be overwritten by the LLM tagger; `cited_by_count` is the citation impact (OpenAlex).

---

## Source adapters
All four expose the **same signature** so `server._fetcher(source)` can swap them: `fetch_metadata(n=100, *, search=None, extra_filters=None, require_pdf=True) -> Iterator[Paper]`. Each yields up to `n` open-access papers and (when `require_pdf`) skips items with no PDF.

### `app/openalex.py`
- **`reconstruct_abstract(inv_index) -> str | None`** — rebuild readable text from OpenAlex's inverted-index abstract.
- **`parse_work(w) -> Paper`** — convert one OpenAlex work into a `Paper`: authors + institution countries, journal, date, DOI, abstract, primary topic (`theme`), `cited_by_count`, and a **ranked, de-duplicated** list of OA PDF URLs (repositories first).
- **`fetch_metadata(...)`** — cursor-paginated; filters `is_oa:true` (+ `has_fulltext:true` when `require_pdf`) and any `extra_filters` (the date range). **The only source that applies date filters.**

### `app/arxiv.py`
- **`parse_entry(e) -> Paper`** — parse one Atom entry: title, authors, summary (abstract), primary category (`theme`), DOI, and the PDF link (derived from the `/abs/` id if absent).
- **`fetch_metadata(...)`** — query the arXiv Atom API, sorted by relevance; one 429 back-off retry. `extra_filters` (dates) ignored.

### `app/pubmed.py`
- **`parse_summary(uid, rec) -> Paper`** — build a `Paper` from an `esummary` record: title, authors, journal, date, DOI, and the PMC PDF URL. Abstract comes from the PDF later.
- **`fetch_metadata(...)`** — search the PMC **open-access subset** (`esearch`) then fetch metadata (`esummary`); honours NCBI's rate limits.

### `app/crossref.py`
- **`parse_item(it) -> Paper`** — parse one Crossref work: title, authors, journal, date, DOI, subject (`theme`), JATS-stripped abstract, and `application/pdf` links.
- **`fetch_metadata(...)`** — cursor-paginated; keeps items exposing an open PDF link (bounded deep paging to find them).

---

## `app/download.py`
Download OA PDFs and extract text, bounded and crash-safe. `_DL = CONFIG["download"]`.

- **`_fetch_pdf_bytes(url, deadline) -> bytes | None`** — stream a PDF; bail early if it isn't a PDF, exceeds `max_pdf_bytes`, or passes `deadline` (a `time.monotonic()` wall-clock budget). Uses `BROWSER_UA`.
- **`_extract_text(data, max_chars, deadline) -> str`** — PyMuPDF text extraction with **MuPDF errors silenced**, a per-page deadline, and corrupt pages skipped — so a malformed PDF (e.g. some Springer/Nature files) can't crash or hang the app.
- **`_extract(data, max_chars, deadline) -> str`** — run extraction in-thread, or in a **process pool** (`parse_in_process`) for hard-timeout / crash isolation.
- **`download_fulltext(paper, *, max_chars=…, deadline_s=…) -> Paper`** — try the paper's ranked candidate URLs within a per-paper budget; set `paper.content` on the first parseable PDF and record the working `pdf_url`. **Never raises.**
- **`download_many(papers, *, workers=…, progress=None) -> list[Paper]`** — download concurrently with a `ThreadPoolExecutor`; `progress(done, total, paper)` fires once per finished paper in the calling thread. (The server uses `download_fulltext` directly in its pipelined build; `download_many` powers the notebook/CLI path.)

---

## `app/system.py`
Resource detection and live metrics (container/cgroup-aware). 

- **`available_cpus()` / `worker_count()` / `download_workers()`** — CPU detection and worker sizing. Downloads are I/O-bound, so `download_workers()` **oversubscribes**: `CPU threads × io_multiplier`, capped at `io_workers_cap`.
- **`_mem_limit_bytes()` / `_mem_used_bytes()`** — RAM ceiling + current usage (honours cgroup limits).
- **`ram_paper_cap()` / `effective_max_papers()`** — RAM-based cap on paper count.
- **`papers_for_target(done, baseline_used, target_pct)`** — suggested paper count to stay under a RAM target (used by the OOM guard).
- **`metrics() -> dict`** — CPU %, RAM %, RAM used/total, network throughput — the System panel feed.
- **`log_resources()`** — verbose startup log of every resource calculation.

---

## `app/corpus.py`
DataFrame assembly, saving, and the on-disk cache. `COLUMNS` defines the output column order.

- **`build_corpus(n=25, *, search=None, extra_filters=None, with_fulltext=True, with_theme=False, workers=…) -> DataFrame`** — fetch metadata, optionally download full text and LLM-tag themes, then return the canonical-column DataFrame. (Notebook/CLI path.)
- **`save_corpus(df, out=None) -> None`** — write `<out>.parquet` + `<out>.csv`, creating parent dirs.
- **`cache_key(topic, date_from, date_to, n, source="openalex") -> str`** — content key for the on-disk cache (namespaced by source).
- **`save_to_cache` / `load_from_cache` / `load_last` / `list_cached` / `load_with_topic`** — persist and reload corpora so identical requests are instant and the last corpus resumes after a restart; `list_cached`/`load_with_topic` back the multi-corpus switcher.

---

## `app/theme.py`
Optional LLM theme tagging.

- **`SYSTEM`** — system prompt asking for a 1–4 word theme tag.
- **`tag_theme(paper, client) -> Paper`** — set `paper.theme` from the title + abstract using an `anthropic.Anthropic` client. Used only when theme tagging is enabled.

---

## `app/ollama_client.py`
Local LLM access. `_OLLAMA = CONFIG["ollama"]`; a keep-alive `_SESSION` reuses connections.

- **`list_models() -> list[str]`** — installed model names via `/api/tags`; `[]` if Ollama is unreachable.
- **`pick_model() -> str | None`** — `OLLAMA_MODEL`/config value if set, else the first installed model, else `None`.
- **`_extra() -> dict`** — shared request extras applied to every generation call: `keep_alive` (keep the model resident) and `options.num_ctx` / `num_predict`.
- **`warm_model(model=None) -> None`** — preload the model via an empty `/api/generate` so the first real question doesn't pay a cold load. No-op if no model.
- **`chat(question, context, model) -> str`** — non-streaming grounded answer (the `/ask` fallback).
- **`chat_stream(question, context, model) -> Iterator[str]`** — stream the answer in chunks (what the UI uses).
- **`embed(texts, model) -> list`** — embedding vectors via `/api/embed` (falls back to `/api/embeddings`). Powers retrieval re-ranking.
- **`expand_query(question, model, n=3) -> list`** — ask the model for alternative phrasings (multi-query expansion).
- **`verify_claims(answer, context, model) -> str`** — fact-check an answer against the sources; returns a short note.

---

## `app/retrieval.py`
Passage-level RAG. `_R = CONFIG["retrieval"]`.

- **`_index(df)`** — build a **BM25 index over passages** (title+abstract + overlapping content chunks), cached per corpus.
- **`_best_excerpt(text, q_tokens, size)`** — pick the most query-relevant window of a passage (not just the head).
- **`_embeddings_enabled()` / `_embed_docs()` / `_rerank()`** — optional embedding re-rank of BM25 candidates by cosine similarity, with a persistent content-addressed embedding cache (`<cache>/embeddings.json`). Falls back to BM25 if no embed model.
- **`_expand(question)`** — multi-query variants (config-gated).
- **`build_context(df, question, k=None, budget=None) -> (context_str, sources)`** — fuse the question (+ variants) over BM25, optionally embedding-re-rank, take the top `k`, and assemble numbered `[1] [2] …` excerpts up to `budget` characters. Returns the context string and source metadata dicts.

---

## `app/server.py`
The Django application. State: `JOBS` (job_id → progress), `CORPUS` (current DataFrame), an LRU of recent corpora, `DL` (live download stats), `STATS` (cumulative counters), `_LOCK`.

- **`run_build(job_id, topic, date_from, date_to, n, source="openalex") -> None`** — background worker: cache check → stream metadata from the chosen source → submit downloads as papers arrive (pipelined) → RAM/OOM guard + cancel support + optional checkpoints → assemble + save → update `STATS` → warm the model.
- **`_fetcher(source)`** — return the source's `fetch_metadata` (`openalex`/`arxiv`/`pubmed`/`crossref`).
- **`_warm_async()`** — preload the model in a daemon thread (respects `warm_on_start`).
- **`index` / `build` / `status` / `cancel`** — render the UI; start/inspect/stop a build.
- **`ask` / `ask_stream`** — answer a question (non-streaming JSON / streamed SSE). `ask_stream` also emits the `verify` event and records retrieval/answer timings.
- **`corpus_view` / `corpora_view` / `corpus_select`** — browse the current corpus; list and switch between cached corpora.
- **`download_csv` / `download_parquet` / `download_bibtex` / `download_ris`** — export the corpus.
- **`metrics_view` / `_metrics_payload`** — live system metrics (polling fallback).
- **`stats_view` / `_stats_payload`** — cumulative observability counters (Session-stats dashboard).
- **`events`** — one SSE stream pushing `metrics` + `stats` (+ a job's `status`).
- **`suggest`** — question-bar completions. **`app_css` / `app_js` / `manifest_view` / `sw_js` / `static_asset`** — UI assets + PWA.
- **`run() -> None`** — resume the last corpus, warm the model, and start Django's dev server. Called by `main.py`.
- **`urlpatterns` / `application`** — route table and WSGI app.

---

## Entry points

- **`main.py`** — imports and calls `app.server.run()`.
- **`pipeline.py`** — back-compat shim re-exporting `build_corpus, save_corpus, fetch_metadata, download_fulltext, download_many, Paper` so notebooks can `import pipeline`.
- **`tools/rag_eval.py`** — offline RAG evaluation harness (retrieval/keyword scoring against a golden set).
