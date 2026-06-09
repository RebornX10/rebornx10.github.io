# Testing

The suite is **146 pytest tests**: **144 run fully offline** (all network and LLM calls are mocked, so it finishes in ~2s and is safe for CI) plus **2 opt-in live-Ollama tests** that are skipped unless you set `RUN_OLLAMA_INTEGRATION=1`.

## Running

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

`pytest.ini` sets `testpaths = tests` and quiet output. The same command runs in the GitHub Actions `test` job.

To also exercise a **real** Ollama (chat + embeddings):

```bash
RUN_OLLAMA_INTEGRATION=1 pytest tests/test_integration_ollama.py
```

## How things are mocked

- **HTTP**: tests monkeypatch the shared `app.http.SESSION.get` (and `app.ollama_client._SESSION`) with a `FakeResponse` from `conftest.py` — no real OpenAlex/arXiv/PubMed/Crossref/PDF/Ollama traffic.
- **PDFs**: `conftest.make_pdf_bytes()` builds a tiny real PDF with PyMuPDF, so extraction is exercised for real.
- **Source records**: `conftest.make_work()` returns a representative OpenAlex work; the adapter tests embed sample Atom/JSON payloads.
- **Anthropic**: a `FakeClient` stands in for the theme tagger.
- **Django views**: called directly via `RequestFactory`; `app.server`'s imported functions are monkeypatched (e.g. `fetch_metadata`, `download_fulltext`, `chat_stream`, `pick_model`, cache loaders).

## Shared fixtures (`tests/conftest.py`)

- `pdf_bytes` — valid PDF bytes with extractable text.
- `paper` — a populated `Paper`.
- `FakeResponse` — supports `.json()`, `.iter_content()`, `.raise_for_status()`, `.headers`, `.status_code`.
- `make_work(**over)` — build an OpenAlex work dict (repository + publisher PDF locations, inverted-index abstract, topic, authorships with countries, citation count).

## What each file covers

| File | Focus |
|---|---|
| `test_config.py` | All config sections present; env overrides (incl. `RERANK`, `EMBED_MODEL`, Ollama keys); load without env |
| `test_openalex.py` | `reconstruct_abstract`; `parse_work` fields, **repository-preferred** PDF ranking, de-dup, `cited_by_count`; `fetch_metadata` paging/limits |
| `test_arxiv.py` | Atom parsing, PDF derived from `/abs/`, respects `n` |
| `test_pubmed.py` | `esearch`+`esummary` parsing, PMC PDF URL, year-only dates, empty results |
| `test_crossref.py` | Item parsing, JATS abstract stripping, PDF-link filtering, `require_pdf` toggle |
| `test_download.py` | `_fetch_pdf_bytes` valid/rejects-HTML/byte-cap/deadline; `_extract` in-thread vs pool + timeout; `download_fulltext` fallback/all-fail; `download_many` parallelism + progress |
| `test_system.py` | CPU/RAM detection, worker sizing, paper caps, metrics |
| `test_corpus.py` | `build_corpus` metadata-only vs full text; `save_corpus`; cache round-trip, `list_cached`/`load_with_topic` |
| `test_theme.py` | `tag_theme` sets theme, uses the abstract, skips when empty |
| `test_ollama_client.py` | `list_models`/`pick_model`; `chat`; **keep_alive + num_ctx** sent; `warm_model`; `embed` batch + fallback |
| `test_retrieval.py` | BM25 passage ranking, best-excerpt, embedding re-rank reorders/falls back, multi-query fusion, embedding cache |
| `test_server.py` | `index` render + panels; `build` validation/clamp/**source routing**; `status`; `ask`/`ask_stream` (stream + verify); corpus/corpora/select; CSV/Parquet/BibTeX/RIS; `events` (metrics+stats); `stats`; cancel/checkpoint |
| `test_eval.py` | `tools/rag_eval.py` scoring helpers |
| `test_e2e.py` | Full **build → ask** flow with mocked network + Ollama |
| `test_integration_ollama.py` | **Opt-in**: real chat + `build_context → chat` against a live Ollama |

## Adding tests

- Put new tests in `tests/test_*.py`; reuse `conftest` fixtures.
- Keep them offline — monkeypatch `SESSION.get` / `_SESSION` / `app.server` functions rather than hitting the network.
- For view tests, use `RequestFactory` and rely on the state-clearing fixture in `test_server.py` (it resets `JOBS`/`CORPUS`/the LRU and stubs the cache loaders).

## Continuous integration

- **`ci.yml`** (every push/PR to `master`): **test** (Python 3.11, install deps, `pytest`) + **docker** (`docker build` validates the image). Ollama is mocked, so it's fast.
- **`ollama-integration.yml`** (manual, Actions tab): installs Ollama, pulls `qwen2.5:0.5b` + `nomic-embed-text`, and runs with `RUN_OLLAMA_INTEGRATION=1`.
- **Dependabot**: weekly pip + github-actions update PRs.

See [Deployment](Deployment#continuous-integration) for details.
