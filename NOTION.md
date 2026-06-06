# 🔬 Global Paper Research Assistant — Project Hub

> **How to import into Notion:** New page → `⋯` (top-right) → **Import** → **Markdown & CSV** → pick this file. Or open this file, copy all, and paste into an empty Notion page (Notion converts headings, tables, and `- [ ]` checkboxes automatically). Then drag the top-level sections into sub-pages if you prefer.

A privacy-friendly, fully-local research assistant: search open-access papers (OpenAlex), download + extract full text, and ask questions answered by a local LLM (Ollama) — grounded in the papers, with citations. Runs on your machine, in Docker, in Codespaces, and as a Hugging Face Space. Installable PWA.

- **Live demo:** `https://samdnx-sci-paper-rag.hf.space`
- **Landing page:** `https://rebornx10.github.io`
- **Stack:** Python · Django (single-file server) · OpenAlex API · PyMuPDF · pandas/Parquet · rank-bm25 · Ollama · vanilla JS PWA
- **Status:** 113 tests passing · deployed and live

---

## 1) Overview & Architecture

**Pipeline:** topic → OpenAlex metadata (cursor-paged, `select=` fields) → parallel PDF download (I/O-oversubscribed thread pool, pipelined with the search) → PyMuPDF text extraction (bounded, crash-safe) → pandas DataFrame → Parquet/CSV + on-disk cache → BM25 (+ optional embedding) retrieval → Ollama streamed answer with citations.

**Key properties**
- Single-process, in-memory `CORPUS`; corpora persisted to an on-disk cache keyed by `topic|dates|n`.
- Container- & RAM-aware: dynamic paper cap, proactive OOM guard, auto-sized download workers (~CPU-threads × multiplier, capped).
- No API key required for the core flow (Claude theme tagging is optional).

**Module map**
| Module | Responsibility |
|---|---|
| `app/server.py` | Django app, routes, build orchestration, SSE, downloads/exports |
| `app/openalex.py` | Metadata fetch + parsing (abstract reconstruction, PDF candidate ranking) |
| `app/download.py` | Streaming PDF fetch + PyMuPDF extraction (in-thread / process-pool) |
| `app/retrieval.py` | BM25 index + best-passage excerpts + optional embedding re-rank |
| `app/ollama_client.py` | Ollama chat (stream), embeddings, model discovery |
| `app/corpus.py` | DataFrame assembly, Parquet/CSV save, on-disk corpus cache |
| `app/system.py` | CPU/RAM detection, worker sizing, paper caps, live metrics |
| `app/theme.py` | Optional Claude theme tagging |
| `app/config.py` | `config.yaml` + env overrides |

---

## 2) Features (current)

### Search & ingestion
- [x] Free-text topic search with optional date range (OpenAlex `is_oa` + `has_fulltext`)
- [x] Four sources behind a selector: **OpenAlex, arXiv, PubMed Central, Crossref** (each open-access PDFs only)
- [x] Parallel PDF download, **pipelined** with the metadata search
- [x] Bounded, crash-safe PDF parsing (per-paper deadline, skips corrupt pages, silenced MuPDF errors)
- [x] Optional **process-pool parsing** for a hard timeout / crash isolation (config-gated)
- [x] Automatic `theme` tag per paper (OpenAlex topic; optional Claude tagging)

### Retrieval & Q&A
- [x] **BM25** retrieval over full text (title + abstract + content), cached per corpus
- [x] Best-passage excerpts (most query-relevant window, not the doc head)
- [x] Optional **embedding re-rank** of BM25 hits via Ollama (`nomic-embed-text`), graceful BM25 fallback
- [x] **Streamed** answers token-by-token (SSE), rendered as **Markdown**
- [x] Hoverable inline **[n] citations** + hoverable source chips
- [x] **Predictive sentence completion** in the question bar (ghost text, Tab/→ to accept)
- [x] Estimated answer time (rolling average, persisted)

### Data & corpus management
- [x] Browse the corpus in a filterable table (expand row → abstract, DOI/PDF links)
- [x] **Download CSV / Parquet**
- [x] On-disk **cache** (identical request = instant load)
- [x] **Resume** last corpus after restart
- [x] **Multi-corpus switcher** (switch topics without rebuilding; in-memory LRU)
- [x] Cancellable builds

### UX / platform
- [x] Installable **PWA** (manifest, service worker, offline app shell, icons)
- [x] Responsive, mobile-first UI; light/dark theme (follows OS) ; reduced-motion support
- [x] Live system panel (CPU/RAM/network/download speed) via **SSE push**, polling fallback
- [x] Allocation panel (workers/threads, RAM allocated, max papers, avg speed, live RAM)
- [x] Build progress + ETA + fun animations + Wikipedia fun-facts
- [x] Build-complete desktop notification; keyboard shortcuts (`/`, Cmd/Ctrl+Enter)

### Performance & ops
- [x] gzip middleware; OpenAlex `select=` payload trimming; Ollama keep-alive session
- [x] I/O-oversubscribed download workers (~6× vs 1-per-CPU, benchmarked)
- [x] RAM-based paper cap + proactive OOM guard + suggested cap
- [x] 113 automated tests (unit + e2e)

### Deployment
- [x] Local (`run.sh`), Docker, Docker Compose (bundled Ollama), GitHub Codespaces
- [x] GitHub Pages landing page (embeds the live Space)
- [x] Hugging Face Spaces (Docker SDK, auto-rebuild on push)

---

## 3) What we've done (changelog by theme)

> Reverse-chronological, grouped. Each line maps to shipped work on `master`.

**Retrieval & answering**
- Streamed answers over SSE (`/ask_stream`) + Markdown rendering + inline citations
- BM25 retrieval over full text with best-passage excerpts (replaced naive term-frequency)
- Chunk-level indexing (passage retrieval on long papers)
- Optional embedding re-rank of BM25 candidates (Ollama embeddings, BM25 fallback) + content-addressed embedding cache
- Multi-query expansion with reciprocal-rank fusion (config-gated)
- Claim → source verification pass (config-gated SSE `verify` event)
- Predictive sentence completion + answer-time estimate
- RAG evaluation harness (`tools/rag_eval.py`)

**Corpus & data**
- Pipelined build + on-disk corpus cache + resume + cancel + incremental Parquet checkpoints
- Browse panel + sortable citation column + CSV / Parquet / BibTeX / RIS export
- Multi-corpus topic switcher (`/corpora`, `/corpus/select`, in-memory LRU) + shareable `?corpus=` deep-links
- Observability counters at `/stats`

**Sources**
- OpenAlex + arXiv + PubMed Central + Crossref adapters behind a Source selector (each filters to open-access PDFs)

**Performance & robustness**
- Download speed optimization (I/O oversubscription, deadlines, chunking) — ~6×
- RAM-based dynamic cap, OOM guard, suggested cap
- Crash-proof PDF parsing (silenced MuPDF errors, bounded page loop) + optional process pool
- Backend quick wins: gzip, OpenAlex `select=`, Ollama keep-alive session
- SSE push for metrics + status (replaced polling), polling fallback

**Platform & UX**
- PWA (manifest, service worker w/ asset-hash cache versioning, icons, install button)
- Mobile-responsive UI, light/dark (OS default), reduced-motion, keyboard shortcuts
- Live metrics + allocation panel; build ETA, stopwatch, animations, Wikipedia facts
- Verbose launch logging (every resource calculation)

**Project**
- Full refactor into a package: tests, `config.yaml`, separated HTML/CSS/JS, Pipfile/requirements
- Deployment matrix: Docker, Compose, Codespaces, Pages, HF Spaces
- Full GitHub Wiki (11 pages)

---

## 4) Wiki (index)

> Source lives in `wiki/` and is published to the GitHub Wiki. One-line summaries:

| Page | What it covers |
|---|---|
| **Home** | Project intro + navigation |
| **Use-Cases** | Who it's for and example workflows |
| **Setup-and-Installation** | Local/venv setup, prerequisites (Ollama) |
| **Configuration** | Every `config.yaml` key + env overrides + tuning notes |
| **Architecture-and-Data-Sources** | Pipeline, OpenAlex, data model |
| **Code-Reference** | Per-module / per-function reference |
| **Web-API** | All HTTP endpoints (`/build`, `/status`, `/cancel`, `/ask`, `/ask_stream`, `/corpus`, `/corpora`, `/corpus/select`, `/download/*`, `/suggest`, `/metrics`, `/events`, PWA) |
| **Testing** | Test layout, how to run, coverage areas |
| **Deployment** | Docker / Compose / Codespaces / Pages / HF Spaces |
| **Troubleshooting** | Common errors and fixes |
| **_Sidebar** | Wiki navigation |

---

## 5) Roadmap (no dates)

> Themed milestones, ordered by priority — not time-boxed.

### Milestone A — Retrieval quality
- Make embedding re-rank first-class (ship an embed model on the Space)
- Multi-query / query expansion before retrieval
- Chunk-level indexing (sub-document passages) instead of whole-doc
- Cross-encoder re-rank option for top candidates

### Milestone B — Answer trustworthiness
- Claim → source verification pass (flag unsupported sentences)
- Structured outputs (summaries, comparison tables, literature reviews)
- Confidence + "insufficient evidence" handling

### Milestone C — Scale
- True streaming-to-disk build (incremental Parquet) for very large corpora
- Persistent vector store for embeddings (avoid recompute)
- Background/queued builds + multiple concurrent corpora

### Milestone D — Sources & coverage
- More sources beyond OpenAlex (arXiv ✅, PubMed Central ✅, Crossref ✅; Unpaywall next)
- Better PDF parsing (tables, figures, references) + OCR fallback
- De-duplication and metadata enrichment

### Milestone E — Product & collaboration
- Saved sessions / shareable corpora
- Auth + per-user workspaces (if multi-user)
- Export to Notion / Zotero / BibTeX

### Milestone F — Ops & quality
- Automated RAG evaluation harness + regression gates
- Observability (timings, retrieval hit-rates, error rates)
- CI matrix incl. an Ollama-backed integration job

---

## 6) Upcoming features (backlog)

| Feature | Why | Size |
|---|---|---|
| Ship `nomic-embed-text` on the HF Space | Make embedding re-rank live in prod | S |
| Relevance score column in the browse table | Surface ranking to the user | S |
| Multi-query expansion | Better recall on vague questions | M |
| Chunk-level retrieval | Precision on long papers | M |
| Persistent embedding cache | Avoid re-embedding per question/corpus | M |
| Claim verification / citation checker | Reduce hallucination | M |
| Literature-review report generator | High-value output artifact | M |
| ~~arXiv / PubMed / Crossref ingestion~~ ✅ | Broaden coverage | L |
| Streaming-to-disk builds | Remove RAM ceiling for huge corpora | L |
| RAG eval harness | Catch answer-quality regressions | M |
| Export to BibTeX / Zotero / Notion | Researcher workflows | S–M |
| Saved & shareable sessions | Collaboration | M |

---

## 7) To-do list

**Now** — done
- [x] HF Space pulls `nomic-embed-text` at startup so embedding re-rank is live (`rerank: auto`)
- [x] Relevance indicator in the browse table (sortable OpenAlex citation count)
- [x] Embeddings setup documented in the wiki (Configuration env vars + tuning note)

**Next** — done
- [x] Persistent embedding cache (content-addressed `<cache>/embeddings.json`)
- [x] Multi-query expansion + reciprocal-rank fusion in `build_context`
- [x] Chunk-level indexing for long documents
- [x] Claim → source verification pass (config `verify`, SSE `verify` event)
- [x] RAG evaluation harness (`tools/rag_eval.py` + golden set + scoring)

**Later** — done / partial
- [x] arXiv + **PubMed Central** + **Crossref** source adapters + Source selector (cache-key namespaced per source)
- [x] Incremental Parquet checkpoints during build (`checkpoint_every`)  · ⬜ full streaming-to-disk rearchitecture
- [x] Export to BibTeX + RIS (Zotero/EndNote); Notion snapshot is this file
- [x] Saved/shareable corpora via `?corpus=<key>` deep-link + Share button
- [x] Observability: `/stats` endpoint (builds, papers, timings)  · ⬜ in-UI dashboard

**Ops / hygiene** — done
- [x] Opt-in CI integration job with a real Ollama model (`ollama-integration.yml`)
- [x] SW cache strategy + offline behaviour documented (wiki Deployment)
- [x] Periodic dependency updates (Dependabot: pip + github-actions, weekly)

---

## 8) AI agents we will need

> A future agentic layer. Each agent has a clear role, I/O, and a suggested model. Status: ⬜ planned · 🟡 partial · ✅ exists.

| Agent | Role | Inputs → Outputs | Model | Status |
|---|---|---|---|---|
| **Orchestrator** | Routes a user request to the right agents; plans multi-step tasks | question/goal → agent calls | small local LLM | ⬜ |
| **Query Planner** | Decomposes a question into sub-queries / search terms | question → sub-queries, filters | small local LLM | ⬜ |
| **Retrieval Agent** | Hybrid BM25 + embedding (+ optional cross-encoder), multi-query fusion | query → ranked passages | embeddings + reranker | 🟡 (BM25 chunks + embed re-rank + multi-query RRF + embed cache) |
| **Summarization Agent** | Per-paper and corpus-level synthesis | passages → summaries | local LLM | 🟡 (streamed answers exist) |
| **Tagging / Theme Agent** | Generate consistent theme/topic tags + taxonomy | title/abstract → tags | OpenAlex topic / Claude | ✅ (theme tagging) |
| **Citation / Verification Agent** | Check each claim against retrieved sources; flag unsupported | answer + sources → verified answer | local LLM | 🟡 (verify pass, config-gated) |
| **Literature-Review Agent** | Produce structured reviews / comparison tables | corpus + outline → report | local LLM | ⬜ |
| **Data-Quality Agent** | De-dup, metadata cleanup, language/quality filters | corpus → cleaned corpus | rules + small LLM | ⬜ |
| **Ingestion / Crawler Agent** | Pull from multiple sources, normalize, resolve PDFs | topic → papers | rules + APIs | 🟡 (OpenAlex + arXiv + PubMed Central + Crossref) |
| **Evaluation Agent** | Score answer quality / retrieval hit-rate; regression gate | Q/A set → metrics | LLM-as-judge | 🟡 (rag_eval harness) |

**Shared infrastructure the agents will need**
- A tool/function interface (search, fetch, embed, summarize, cite)
- A persistent vector store + embedding cache
- An eval/golden dataset and scoring harness
- Guardrails: grounding checks, "insufficient evidence" responses, rate/limits

---

*Generated as a Notion-importable snapshot of the project. Keep this in sync with the repo `wiki/` and `README.md`.*
