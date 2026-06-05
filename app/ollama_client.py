from __future__ import annotations

import logging
import time
from typing import Optional

import requests

from app.config import CONFIG

log = logging.getLogger("ollama")

_OLLAMA = CONFIG["ollama"]


def list_models() -> list[str]:
    try:
        r = requests.get(f"{_OLLAMA['url']}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        log.info("Ollama list_models (%s): %s", _OLLAMA["url"], models or "none")
        return models
    except Exception as e:
        log.warning("Ollama unreachable at %s: %s", _OLLAMA["url"], e)
        return []


def pick_model() -> Optional[str]:
    if _OLLAMA.get("model"):
        return _OLLAMA["model"]
    models = list_models()
    return models[0] if models else None


def chat(question: str, context: str, model: str) -> str:
    prompt = (
        "You are a research assistant. Answer the user's question using ONLY the "
        "paper excerpts below. Cite the paper titles you used. If the excerpts do "
        "not contain the answer, say so plainly.\n\n"
        f"=== PAPER EXCERPTS ===\n{context}\n\n=== QUESTION ===\n{question}"
    )
    log.info("Ollama chat: model=%s, context=%d chars, question=%r",
             model, len(context), question[:80])
    t0 = time.monotonic()
    r = requests.post(
        f"{_OLLAMA['url']}/api/chat",
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
        timeout=_OLLAMA["request_timeout"],
    )
    r.raise_for_status()
    answer = r.json()["message"]["content"].strip()
    log.info("Ollama answered in %.1fs (%d chars)", time.monotonic() - t0, len(answer))
    return answer
