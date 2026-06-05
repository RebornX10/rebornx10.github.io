# Setup & Installation

There are four ways to run sci_paper_llm. All of them serve a web UI on a port (8000 by default) that you open in your browser.

> **Prerequisite for Q&A:** a running [Ollama](https://ollama.com) with at least one model pulled (e.g. `ollama pull llama3.2`). The corpus-building features work without it; only the "Ask a question" step needs a model.

---

## Option 1 — Docker Compose (recommended, fully self-contained)

Bundles Ollama **and** the app. The model is pulled automatically on first run.

```bash
git clone https://github.com/RebornX10/rebornx10.github.io
cd rebornx10.github.io
docker compose up
```

Open <http://localhost:8000>. Stop with `docker compose down` (the model cache and `./data` persist). Choose a model with `OLLAMA_MODEL=qwen2.5:7b docker compose up`.

## Option 2 — Docker, using a host Ollama

```bash
docker build -t sci-paper-llm .
docker run --rm -p 8000:8000 sci-paper-llm          # macOS / Windows
# Linux: add  --add-host=host.docker.internal:host-gateway
```

The image defaults `OLLAMA_URL=http://host.docker.internal:11434` so it reaches Ollama running on your host.

## Option 3 — Global with the helper script

Requires Ollama running globally.

```bash
./run.sh
```

`run.sh` creates/uses a `.venv`, installs dependencies if missing, and starts the app.

## Option 4 — Manual global install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Or with Pipenv:

```bash
pipenv install
pipenv run start
```

---

## GitHub Codespaces (free)

Click **Open in Codespaces** on the repo (or the README badge). The [devcontainer](Deployment#github-codespaces) sets up Python 3.11 + Docker-in-Docker. Once it loads:

```bash
docker compose up
```

The app is forwarded on port **8000** — open it from the *Ports* tab.

---

## Verifying the install

```bash
.venv/bin/python -m pytest      # runs the full test suite (no network needed)
```

A quick smoke test without the web UI:

```python
from pipeline import build_corpus
df = build_corpus(5, with_fulltext=True, with_theme=False)
print(df[["title", "country", "journal", "theme"]])
```

## The Jupyter tutorial

`run.ipynb` walks through building a corpus without the web app — handy for learning the API or batch work. Open it with the project's `.venv` kernel and **Run All**.
