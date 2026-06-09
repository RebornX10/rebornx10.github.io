# Deployment

Ways to ship sci_paper_llm, and the files that drive each.

## Docker image (`Dockerfile`)
`python:3.11-slim`, installs `requirements.txt`, copies the app, runs `python main.py`. Sets container-friendly defaults via env: `HOST=0.0.0.0`, `PORT=8000`, `OPEN_BROWSER=false`, `OLLAMA_URL=http://host.docker.internal:11434`. Includes OCI labels (author, source, license). `.dockerignore` keeps tests/docs/CI out of the image.

```bash
docker build -t sci-paper-llm .
docker run --rm -p 8000:8000 sci-paper-llm
```

The container talks to **Ollama on your host** via `host.docker.internal` (on Linux add `--add-host=host.docker.internal:host-gateway`).

## Docker Compose (`docker-compose.yml`)
Fully self-contained — three services:
- **ollama** — the LLM engine, model cached in a named volume.
- **model-puller** — one-shot; pulls `${OLLAMA_MODEL:-llama3.2}`, then exits; gates the app start.
- **app** — built from the Dockerfile, points `OLLAMA_URL` at the `ollama` service, persists corpora to `./data` (`OUTPUT_BASENAME=data/papers`).

```bash
docker compose up           # first run pulls the model (~GBs)
```

## Global (`run.sh`, `setup.sh`, `Pipfile`)
- `run.sh` — creates/uses `.venv`, installs deps if missing, runs the app.
- `setup.sh` — Pipenv-based bootstrap (installs pipenv, deps, checks Ollama, pulls a model).
- `Pipfile` — `pipenv install`, then `pipenv run start` / `pipenv run test`.

## GitHub Codespaces (`.devcontainer/devcontainer.json`)
Python 3.11 image + Docker-in-Docker, `pip install` of deps, forwards port 8000, binds `0.0.0.0`. In the codespace run `docker compose up` for the full stack.

## GitHub Pages (`docs/`, `.github/workflows/pages.yml`)
The repo is the user site `rebornx10.github.io`. The Pages workflow publishes `docs/` (a static landing page that **embeds the live Hugging Face Space** in an iframe). It uses `actions/configure-pages` with `enablement: true` and deploys on pushes that touch `docs/`.
- Live: https://rebornx10.github.io/

> Pages serves **static files only** — it cannot run the Django app. The landing page embeds the running app hosted on Hugging Face.

## Hugging Face Spaces (`deploy/huggingface/`)
A **Docker** Space that runs Ollama **and** the app together (free CPU tier). Files:
- `README.md` — Space card (`sdk: docker`, `app_port: 7860`).
- `Dockerfile` — installs Ollama (+ `zstd`), runs as user 1000, **clones the app from GitHub at build time**, sets a small default model (`qwen2.5:0.5b`) and `OUTPUT_BASENAME=/tmp/papers`. A cache-bust `ADD` of the master ref ensures rebuilds pull the latest code.
- `start.sh` — starts `ollama serve`, pulls the model, then launches the app on port 7860.

**Deploy:** create a Docker Space and upload those three files (or push via `huggingface_hub`). Update the **Dockerfile** in the Space (or use *Factory rebuild*) to force a fresh clone after code changes.
- Live: https://huggingface.co/spaces/SamDNX/sci_paper_rag

**Caveats:** CPU-only (slow answers), model pulled on cold start, ephemeral storage (corpora reset on restart). Fine for a demo; for real use run globally or on GPU hardware.

## PWA & offline behaviour
The app is an installable PWA. The web manifest is served at `/manifest.webmanifest` and the service worker at `/sw.js` (root scope). Caching strategy (`app/static/sw.js`):

- **App shell** (`/`, CSS, JS, icons, manifest) is precached on install.
- **Navigations** are network-first, falling back to the cached shell when offline — so the UI still loads without a connection.
- **Static assets** use stale-while-revalidate.
- **Live API calls** (`/build`, `/ask_stream`, `/events`, `/corpus*`, `/download/*`, `/stats`, …) are never cached — they always hit the network.

The cache name embeds an asset hash injected by the server (`_SW_VERSION`), so deploying changed HTML/CSS/JS automatically busts old caches; no manual version bump needed. Note that **building corpora and asking questions require connectivity** (OpenAlex/arXiv + Ollama); offline mode only guarantees the shell loads (the source APIs — OpenAlex/arXiv/PubMed/Crossref — and Ollama all need connectivity).

**Install:** open the app over HTTPS (e.g. the Hugging Face Space URL) → browser "Install app" / "Add to Home Screen". Installation isn't offered inside a cross-origin iframe (e.g. the embed on the Pages site) — use the Space URL directly.

## Continuous integration
- **`ci.yml`** (every push/PR to `master`): **test** (Python 3.11, install deps, `pytest`) + **docker** (`docker build` validates the image). Ollama is mocked, so it's fast; both must pass for the CI badge to be green.
- **`ollama-integration.yml`** (manual, Actions tab): installs Ollama, pulls `qwen2.5:0.5b` + `nomic-embed-text`, and runs the suite with `RUN_OLLAMA_INTEGRATION=1` to exercise the real chat/embedding path.
- **Dependabot** (`.github/dependabot.yml`): weekly pip + github-actions update PRs.

## Releases
Tagged with annotated git tags (e.g. `v0.1.0`). Create a GitHub Release from a tag in the UI (or with `gh release create`).
