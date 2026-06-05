# Use Cases

sci_paper_llm is useful any time you want a **structured, queryable corpus of open-access papers** without scraping pirate sites.

## 1. Literature review / scoping
Pull the recent open-access literature on a topic ("perovskite solar cells", 2023→), skim the auto-generated theme tags and journals, then ask the global model *"What are the main approaches to improving stability?"* and get an answer grounded in the downloaded papers, with the source titles cited.

## 2. Building an NLP / RAG dataset
Export a clean `papers.parquet` / `papers.csv` with full text and metadata to use as training/eval data, a retrieval corpus, or input to your own pipelines. Columns are consistent and machine-friendly.

## 3. Private, offline question answering
Because answers come from a **global Ollama model**, no paper text or questions leave your machine. Good for sensitive research environments or when you simply don't want to send data to a cloud API.

## 4. Bibliometric / metadata analysis
Even without downloading PDFs (`with_fulltext=False`), you get authors, journals, publication dates, countries (from author institutions), and OpenAlex topics — enough for quick descriptive analysis in pandas.

## 5. Teaching / demos
The bundled Jupyter tutorial (`run.ipynb`) and the one-click Hugging Face Space make it easy to demonstrate an end-to-end "search → download → ask" pipeline.

## What it is **not**

- **Not a paywall bypass.** It only fetches papers that have a legal open-access copy. Expect ~75–90% full-text coverage; the rest are metadata-only.
- **Not a large-scale crawler (out of the box).** The whole corpus is held in memory during a build, so very large pulls (thousands+) need a machine with enough RAM, and ideally a streaming refactor.
- **Not a production multi-user service.** It uses Django's dev server and in-memory state — perfect for a single user globally or a demo Space.

## Typical flow

1. Enter a **topic** and an optional **date range**.
2. Click **Download topic** — papers are fetched and parsed in parallel (with a live stopwatch + progress bar).
3. Once done, the **question box** unlocks — ask anything; the model answers from the corpus with citations.
4. The corpus is also saved to disk (`papers.parquet` / `papers.csv`).
