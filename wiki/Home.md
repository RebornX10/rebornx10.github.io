# sci_paper_llm — Global Paper Research Assistant

**Search open-access research papers, download their full text, and ask questions about them — answered by a local LLM, grounded in the papers, with citations. Everything runs on your own machine.**

You type a topic (e.g. *"CRISPR gene editing"*). The app finds open-access papers, downloads and reads their PDFs, and builds a searchable corpus. Then you ask questions in plain English and get a streamed, cited answer that only uses those papers.

- **Live demo:** https://huggingface.co/spaces/SamDNX/sci_paper_rag
- **Project page:** https://rebornx10.github.io/
- **Source:** https://github.com/RebornX10/rebornx10.github.io

---

## What it does, in three steps

1. **Search** — pick a topic, an optional date range, how many papers, and a source (OpenAlex, arXiv, PubMed Central, or Crossref). The app pulls metadata for open-access papers only.
2. **Download & read** — PDFs are fetched in parallel and their text extracted, while the search is still running. You watch live progress, a stopwatch, and an ETA.
3. **Ask** — once the corpus is built, the question box unlocks. Your question is matched against the papers and sent to your local Ollama model, which streams back a Markdown answer with inline `[1]`-style citations you can hover.

## Why it exists

Most "get papers in bulk" tools rely on piracy. This project deliberately uses **open catalogues** ([OpenAlex](https://openalex.org), arXiv, PubMed Central, Crossref) and only ever downloads PDFs from their **legal open-access locations**. The result is a clean, reproducible corpus you can analyse in pandas or feed to an LLM — and because the LLM is local ([Ollama](https://ollama.com)), no paper text or question ever leaves your machine.

## Key features

- 🔎 **Four sources** behind one selector: OpenAlex, arXiv, PubMed Central, Crossref (open-access PDFs only).
- ⬇️ **Fast parallel downloads** pipelined with the search; crash-safe PDF text extraction.
- 💬 **Streamed, cited answers** from a local LLM, grounded by **BM25 passage retrieval** (with optional embedding re-rank and a claim-verification pass).
- 🗂️ **Browse & export** the corpus as a sortable table, or download CSV / Parquet / BibTeX / RIS.
- 🔀 **Multi-corpus switcher**, on-disk cache, resume-after-restart, shareable `?corpus=` links.
- 📊 **Live System panel** (CPU / RAM / network) and a **Session-stats dashboard** (builds, papers, questions, timings) pushed over Server-Sent Events.
- 📱 **Installable PWA** — responsive, works on mobile browsers, loads its shell offline.
- 🐳 Runs locally, in Docker / Compose (bundled Ollama), in GitHub Codespaces, or as a Hugging Face Space.

## At a glance

| | |
|---|---|
| Language | Python 3.11 (runs on 3.9+) |
| Web framework | Django (single-file app config) |
| LLM | Ollama (local), optional Anthropic for theme tagging |
| Sources | OpenAlex · arXiv · PubMed Central · Crossref |
| PDF text | PyMuPDF |
| Retrieval | rank-bm25 over passages (+ optional Ollama embeddings) |
| Data | pandas → Parquet / CSV (+ BibTeX / RIS) |
| Tests | pytest — 146 tests (144 offline, 2 opt-in live-Ollama) |
| Hosting | Local, Docker, Codespaces, Hugging Face Spaces |

## Where to go next

- **New here?** Start with **[Use Cases](Use-Cases)**, then **[Setup & Installation](Setup-and-Installation)**.
- **Want it faster / tuned?** See **[Configuration](Configuration)** (including the *Slow answers* note).
- **Curious how it works?** **[Architecture & Data Sources](Architecture-and-Data-Sources)**.
- **Hacking on the code?** **[Code Reference](Code-Reference)** and **[Testing](Testing)**.
- **Calling it from scripts?** **[Web API](Web-API)**.
- **Shipping it?** **[Deployment](Deployment)**.
- **Stuck?** **[Troubleshooting](Troubleshooting)**.
