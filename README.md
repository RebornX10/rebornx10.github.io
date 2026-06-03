# 🔬 sci_paper_llm — Local Paper Research Assistant

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/RebornX10/sci_paper_llm)
[![CI](https://github.com/RebornX10/sci_paper_llm/actions/workflows/ci.yml/badge.svg)](https://github.com/RebornX10/sci_paper_llm/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Build a dataset of **open-access** scientific papers and ask questions about them with a **local LLM** (Ollama) — all running on your machine.

Papers come from [OpenAlex](https://openalex.org) (a free, open index of ~250M scholarly works) and are downloaded only from their legal open-access locations. Each paper becomes a row with `authors, title, content, date, country, journal, theme`, and you can query the corpus in natural language through a small web UI.

## Features

- 🔎 Search any topic with an optional date range
- ⬇️ Parallel PDF download + full-text extraction with a live progress bar
- 🏷️ Automatic `theme` tag per paper (OpenAlex topic; optional Claude tagging)
- 💬 Ask questions answered by your local Ollama model, grounded in the papers
- 🐳 Fully containerised — bundled Ollama + app via Docker Compose
- ☁️ Runs free in GitHub Codespaces

## Architecture

```
OpenAlex API ──► metadata (authors, title, date, journal, country, theme)
      ▼
Download PDFs (parallel, OA locations) ──► PyMuPDF text  → content
      ▼
pandas DataFrame ──► papers.parquet / papers.csv
      ▼
Ask a question ──► retrieve relevant papers ──► Ollama answer + citations
```

## Quick start

### Option 1 — Docker Compose (recommended, fully self-contained)

Bundles Ollama and the app; the model is pulled automatically on first run.

```bash
docker compose up
```

Open <http://localhost:8000>. Stop with `docker compose down` (the model cache and `./data` persist). Pick a model with `OLLAMA_MODEL=qwen2.5:7b docker compose up`.

### Option 2 — Docker, using an Ollama already running on your host

```bash
docker build -t sci-paper-llm .
docker run --rm -p 8000:8000 sci-paper-llm          # macOS / Windows
# Linux: add  --add-host=host.docker.internal:host-gateway
```

### Option 3 — Local (no Docker)

Requires [Ollama](https://ollama.com) running locally.

```bash
./run.sh
```

`run.sh` creates/uses a `.venv`, installs dependencies, and starts the app.

## GitHub Codespaces (free hosting)

Click the **Open in Codespaces** badge above. Once the codespace is ready, run:

```bash
docker compose up
```

The app is forwarded on port **8000** — open it from the *Ports* tab.

## Configuration

All variables live in [config.yaml](config.yaml) and can be overridden with environment variables:

| Env var | config.yaml | Default | Purpose |
|---|---|---|---|
| `HOST` | `server.host` | `127.0.0.1` | Bind address (`0.0.0.0` in containers) |
| `PORT` | `server.port` | `8000` | Web server port |
| `OPEN_BROWSER` | `server.open_browser` | `true` | Auto-open browser on start |
| `WORKERS` | `download.workers` | `12` | Parallel PDF downloads |
| `OUTPUT_BASENAME` | `download.output_basename` | `papers` | Output path for the saved corpus |
| `OPENALEX_MAILTO` | `openalex.mailto` | — | Your email (OpenAlex polite pool) |
| `OLLAMA_URL` | `ollama.url` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `ollama.model` | auto-detect | Model used for answers |

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

There is also a Jupyter tutorial in [run.ipynb](run.ipynb) for building corpora without the web app.

## Project structure

```
app/              core package (config, openalex, download, corpus, ollama, retrieval, server)
app/templates/    web UI
tests/            unit + end-to-end tests
main.py           entry point
config.yaml       all tunable variables
Dockerfile        application image
docker-compose.yml  bundled Ollama + app
.devcontainer/    GitHub Codespaces setup
.github/workflows/  CI (tests + Docker build)
```

## Author

**Samuel Adone** — GitHub [@RebornX10](https://github.com/RebornX10)

## License

[MIT](LICENSE) © 2026 Samuel Adone
