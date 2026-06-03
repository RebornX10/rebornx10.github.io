from __future__ import annotations

from typing import Optional

import requests

from app.config import CONFIG

_OLLAMA = CONFIG["ollama"]


def list_models() -> list[str]:
    try:
        r = requests.get(f"{_OLLAMA['url']}/api/tags", timeout=5)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
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
    r = requests.post(
        f"{_OLLAMA['url']}/api/chat",
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
        timeout=_OLLAMA["request_timeout"],
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()
