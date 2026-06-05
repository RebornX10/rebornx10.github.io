# sci_paper_llm — Global Paper Research Assistant

Build a dataset of **open-access** scientific papers from [OpenAlex](https://openalex.org), download their full text, and ask questions about them with a **global LLM** ([Ollama](https://ollama.com)) — all on your own machine.

Each paper becomes a row with: `authors, title, content, date, country, journal, theme`. A small web UI lets you search a topic, watch the download progress, and query the corpus in natural language with cited answers.

- **Live demo:** https://huggingface.co/spaces/SamDNX/sci_paper_rag
- **Project page:** https://rebornx10.github.io/
- **Source:** https://github.com/RebornX10/rebornx10.github.io

## Why it exists

Most tools that "get papers in bulk" rely on piracy. This project deliberately uses **OpenAlex** (a free, open index of ~250M scholarly works) and only ever downloads PDFs from the **legal open-access locations** OpenAlex points to. The result is a clean, reproducible corpus you can analyse or feed to an LLM.

## At a glance

| | |
|---|---|
| Language | Python 3.11 (runs on 3.9+) |
| Web framework | Django (single-file app config) |
| LLM | Ollama (global), optional Anthropic for theme tagging |
| Metadata | OpenAlex API |
| PDF text | PyMuPDF |
| Data | pandas → Parquet / CSV |
| Tests | pytest (60 tests) |
| Packaging | Docker, Docker Compose, Pipfile, requirements.txt |
| Hosting | Global, Docker, GitHub Codespaces, Hugging Face Spaces |

## Where to go next

- New here? Start with **[Use Cases](Use-Cases)** then **[Setup & Installation](Setup-and-Installation)**.
- Want to tune it? See **[Configuration](Configuration)**.
- Curious how it works? **[Architecture & Data Sources](Architecture-and-Data-Sources)**.
- Hacking on the code? **[Code Reference](Code-Reference)** and **[Testing](Testing)**.
- Shipping it? **[Deployment](Deployment)**.
