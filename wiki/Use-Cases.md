# Use Cases

sci_paper_llm is useful any time you want a **structured, queryable corpus of open-access papers** — and grounded answers about them — without scraping pirate sites.

## 1. Literature review / scoping
Pull recent open-access work on a topic ("perovskite solar cells", 2023→) from the most relevant **source** (OpenAlex for breadth, arXiv for preprints, PubMed for biomedicine), skim the theme tags, journals, and **citation counts** in the browse table, then ask *"What are the main approaches to improving stability?"* and get a **streamed answer with inline citations** grounded only in the downloaded papers. Turn on the **verification pass** to flag any claim not supported by the sources.

## 2. Building an NLP / RAG dataset
Export a clean corpus — **CSV, Parquet, BibTeX, or RIS** — with full text and consistent metadata, for use as training/eval data, a retrieval corpus, or input to your own pipelines.

## 3. Private, offline question answering
Answers come from a **local Ollama model**, so no paper text or question leaves your machine — good for sensitive research environments, or when you simply don't want to send data to a cloud API.

## 4. Bibliometric / metadata analysis
Even without full text, you get authors, journals, dates, countries (from author institutions), topics, and citation counts — enough for quick descriptive analysis in pandas.

## 5. Comparing sources
Build the same topic from different sources and switch between them instantly with the **multi-corpus switcher** (each is cached separately) to compare coverage — e.g. arXiv preprints vs. PubMed Central vs. the broad OpenAlex index.

## 6. Teaching / demos
The bundled Jupyter tutorial (`run.ipynb`) and the one-click Hugging Face Space make it easy to demonstrate an end-to-end "search → download → ask" pipeline. The live **System** and **Session-stats** panels make the resource usage and timings visible.

## What it is **not**

- **Not a paywall bypass.** It only fetches papers with a legal open-access copy. Expect ~75–90% full-text coverage; the rest are metadata-only.
- **Not a large-scale crawler (out of the box).** The whole corpus is held in memory during a build, so very large pulls (thousands+) need enough RAM. Incremental Parquet checkpoints exist, but a full streaming-to-disk mode is not yet implemented.
- **Not a production multi-user service.** It uses Django's dev server and in-memory state — perfect for a single local user or a demo Space.

## Typical flow

1. Enter a **topic**, an optional **date range**, a paper count, and a **source**.
2. Click **Download topic** — papers are fetched and parsed in parallel, with a live progress bar, stopwatch, and ETA. (Identical past requests load instantly from cache.)
3. When it finishes, the model is **pre-warmed** and the **question box** unlocks — ask anything and watch the answer stream in with citations.
4. **Browse** the corpus in the sortable table and **export** it; the corpus is also saved to disk and **resumes after a restart**.
