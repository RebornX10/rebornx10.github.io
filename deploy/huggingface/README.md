---
title: sci_paper_llm
emoji: 🔬
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# sci_paper_llm — live demo

Build open-access scientific-paper datasets from [OpenAlex](https://openalex.org) and
query them with a global LLM, running entirely inside this Space.

> **Free CPU Space caveats:** the LLM runs on CPU with a small model
> (`qwen2.5:0.5b` by default), so answers are slow and the model is pulled on
> cold start. For full speed, use a GPU Space or run globally with Docker Compose.
> Change the model with the `OLLAMA_MODEL` Space variable.
