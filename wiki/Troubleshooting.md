# Troubleshooting

## "No Ollama model found" banner / `/ask` says no model
Ollama isn't running or has no model. Start it and pull one:
```bash
ollama pull llama3.2
```
Reload the page. In Docker, check `OLLAMA_URL` points at a reachable Ollama (host: `host.docker.internal`; Compose: `http://ollama:11434`).

## Q&A is slow
First, check **which half** is slow in the **Session stats** panel (right sidebar): *Avg retrieval* vs *Avg answer*.

- **Slow answer, especially the first one or after a pause** → usually a **cold model load**. The app already mitigates this: it sends `keep_alive` (keeps the model in memory) and **warms** the model at startup / after each build. If you still see it, raise `OLLAMA_KEEP_ALIVE` (e.g. `-1` to never unload) and make sure `warm_on_start` is on.
- **Consistently slow answers even when warm** → it's the model/hardware (e.g. CPU on the free Hugging Face Space). Use a smaller model (`OLLAMA_MODEL=llama3.2:1b` / `qwen2.5:0.5b`) or GPU hardware, and/or lower `retrieval.context_budget` to shrink the prompt.
- **Slow retrieval** → the first question after a build embeds the candidate papers (one-time, then cached). Set `RERANK=off` to use pure BM25 (faster, slightly lower precision).

Corpus building is unaffected — these only touch question answering. See [Configuration → Slow answers](Configuration#tuning-notes).

## Few papers have `content` (low full-text coverage)
Normal — expect ~75–90%. Some papers' only OA copy is publisher-hosted and blocks bots (`403`), or is slow and hits the per-paper deadline. Filtering to recent papers (`from_publication_date:2022-01-01`) improves coverage. Tune `download.paper_deadline_s` / `read_timeout` if you want to wait longer.

## A source returns few or no papers
Each source keeps only **open-access items with a downloadable PDF**, so a niche query can come back small. Notes per source: **arXiv / PubMed / Crossref ignore the date range** (only OpenAlex filters by date); **Crossref** keeps only items exposing an open `application/pdf` link, so it's the sparsest; **PubMed** searches the PMC open-access subset; **arXiv** may briefly rate-limit (`429`) repeated queries — the adapter backs off and retries once. Try a broader query, a different source, or `OpenAlex` (the broadest) if you get too few.

## Build is slow / stalls near the end
Downloads are parallel, but the batch finishes only when the slowest paper does (capped by `paper_deadline_s`). Raise `workers` up to ~16 (diminishing returns after that, since one straggler hits the deadline floor). Lower `paper_deadline_s` to trade coverage for speed.

## "Repository not found" pushing to the wiki
The GitHub wiki repo (`<repo>.wiki.git`) only exists after you **enable Wikis** (Settings → Features) **and create the first page** in the UI. Then `git clone …wiki.git` works.

## Hugging Face Space shows old code after a change
The Space's `Dockerfile` `git clone`s the app, and that layer can be **cached**. Either re-upload the (cache-busting) `Dockerfile` from `deploy/huggingface/`, or use **Settings → Factory rebuild** (no-cache) once.

## `ModuleNotFoundError` (pandas, fitz, django…)
Wrong interpreter. Use the project venv: `.venv/bin/python …`, or in a notebook select the `.venv` kernel. Reinstall with `pip install -r requirements.txt`.

## GitHub Pages page is blank / 404
The Pages workflow may not have been able to auto-enable Pages. In the repo: **Settings → Pages → Build and deployment → Source: GitHub Actions**, then re-run the "Deploy Pages" workflow.

## Large pulls crash (out of memory)
The entire corpus (with full text) is held in RAM during a build. Lower `n` / `max_chars`, run on a machine with more RAM, or request a streaming refactor (incremental write-to-disk). Don't attempt thousands of papers on a small free Space.

## Corpus disappears after restart
In-memory `CORPUS` and (on ephemeral hosts) `/tmp` reset on restart. The saved `papers.parquet`/`.csv` persist only where the filesystem persists — mount a volume (`OUTPUT_BASENAME=data/papers` + `-v ./data:/app/data`) to keep them.

## Docker on macOS: `docker info` fails
`brew install docker` installs only the CLI. You need an engine — install Docker Desktop (`brew install --cask docker`, requires your password) or Colima (`brew install colima && colima start`).
