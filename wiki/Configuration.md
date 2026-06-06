# Configuration

All tunable settings live in **`config.yaml`** at the repo root. Every value can be overridden at runtime with an environment variable, which is how the Docker/Compose/Codespaces/HF deployments adjust behaviour without editing files.

Config is loaded once by [`app/config.py`](Code-Reference#appconfigpy) into the `CONFIG` dict.

## `config.yaml` reference

```yaml
server:
  host: 127.0.0.1        # bind address (use 0.0.0.0 in containers)
  port: 8000             # web server port
  open_browser: true     # auto-open a browser tab on start

openalex:
  mailto: you@example.com           # your email -> OpenAlex "polite pool" (faster)
  per_page: 200                     # OpenAlex page size (max 200)
  default_search: null              # default free-text query (null = all fields)
  default_filters: "from_publication_date:2022-01-01"  # default OpenAlex filter
  max_papers: 25                    # default "Max papers" value in the UI
  max_papers_cap: 1000000           # hard ceiling; RAM cap + runtime guard are the real limits

download:
  # Downloads are I/O-bound, so concurrency is decoupled from CPU count and
  # oversubscribed: workers = available CPU threads x io_multiplier, capped at
  # io_workers_cap. Benchmarked ~6x faster than 1-worker-per-CPU.
  workers: null            # null = auto (I/O oversubscription); set an int to force
  io_multiplier: 8         # download workers per available CPU thread
  io_workers_cap: 32       # ceiling on concurrent downloads
  thread_fraction: 0.8     # share of CPU threads for CPU-bound work (PDF parse sizing)
  paper_deadline_s: 15     # wall-clock budget per paper across all candidate URLs
  parse_in_process: false  # parse PDFs in a process pool (hard timeout + crash isolation)
  max_pdf_bytes: 80000000  # stop reading PDFs larger than this (~80 MB)
  connect_timeout: 5       # per-request connect timeout (s)
  read_timeout: 20         # per-request read timeout (s)
  max_chars: 2000000       # truncate extracted text to this many characters
  output_basename: papers  # output path -> <basename>.parquet / .csv
  ram_fraction: 0.85       # fraction of RAM the corpus may use (peak)
  ram_per_paper_mb: 0.06   # est. peak memory per paper (runtime guard is the real safety net)
  ram_guard_pct: 85        # abort a build if projected peak RAM would exceed this
  ram_target_pct: 80       # suggested cap aims to keep peak RAM at/below this

ollama:
  url: http://localhost:11434  # Ollama endpoint
  model: null                  # null = auto-detect first installed model
  request_timeout: 300         # seconds to wait for an answer

retrieval:
  top_k: 5             # how many papers to feed the model per question
  context_budget: 9000 # max characters of context sent to the model
  rerank: auto         # embedding re-rank of BM25 hits: auto | on | off
  embed_model: nomic-embed-text  # Ollama embedding model (auto-used only if installed)
  rerank_k: 30         # BM25 candidates to re-rank by embedding similarity

theme:
  anthropic_model: claude-opus-4-8  # model used only if with_theme=True (needs ANTHROPIC_API_KEY)
```

## Environment-variable overrides

These are applied on top of `config.yaml` by `app/config.py`:

| Env var | Overrides | Type |
|---|---|---|
| `HOST` | `server.host` | str |
| `PORT` | `server.port` | int |
| `OPEN_BROWSER` | `server.open_browser` | bool (`1/true/yes/on`) |
| `OPENALEX_MAILTO` | `openalex.mailto` | str |
| `MAX_PAPERS_CAP` | `openalex.max_papers_cap` | int |
| `WORKERS` | `download.workers` | int |
| `OUTPUT_BASENAME` | `download.output_basename` | str |
| `PARSE_IN_PROCESS` | `download.parse_in_process` | bool |
| `OLLAMA_URL` | `ollama.url` | str |
| `OLLAMA_MODEL` | `ollama.model` | str |
| `RERANK` | `retrieval.rerank` | str (`auto`/`on`/`off`) |
| `EMBED_MODEL` | `retrieval.embed_model` | str |
| `RERANK_K` | `retrieval.rerank_k` | int |

Example:

```bash
PORT=9000 WORKERS=16 OLLAMA_MODEL=llama3.2:1b ./run.sh
```

A custom config file path can be set with `CONFIG_FILE=/path/to/config.yaml`.

## Tuning notes

- **Embedding re-rank:** retrieval re-ranks the BM25 top-`rerank_k` by semantic similarity when an Ollama embedding model is installed. To enable it locally: `ollama pull nomic-embed-text` (then `rerank: auto` activates it automatically). Force it with `RERANK=on`, or disable with `RERANK=off`. On the Hugging Face Space the embed model is pulled at startup (`EMBED_MODEL`), so re-rank is live there. With no embed model present it transparently falls back to pure BM25.
- **Download concurrency:** PDF downloads are I/O-bound, so `workers` defaults to `null` and is auto-computed as `available CPU threads x io_multiplier`, capped at `io_workers_cap` (e.g. 16 on a 2-vCPU free Space, 32 on a big box). Benchmarks show ~6x throughput vs. one worker per CPU. Set `workers` to an int (or the `WORKERS` env var) to force a fixed value.
- **Speed vs. coverage:** once concurrency is high, the wall-clock floor is the per-paper "straggler" — one slow PDF holds a slot until `paper_deadline_s`. Lowering `download.paper_deadline_s` cuts that tail and makes builds faster, at the cost of dropping a few slow-but-valid PDFs.
- **Memory:** the whole corpus (full text included) is held in RAM during a build. `max_chars` caps per-paper text; `max_papers_cap` caps the count. Keep these sane for the machine you run on (especially small free Spaces).
- **LLM theme tags:** by default `theme` comes free from OpenAlex topics. Set `ANTHROPIC_API_KEY` and call with `with_theme=True` to generate custom tags with Claude instead.
- **Anthropic API & prompt caching:** if you extend the theme tagger or add other Claude calls, see the Claude API skill for prompt-caching guidance.
