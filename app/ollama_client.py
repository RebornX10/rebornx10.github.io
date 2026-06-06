from __future__ import annotations

import json
import logging
import time
from typing import Iterator, Optional

import requests

from app.config import CONFIG

log = logging.getLogger("ollama")

_OLLAMA = CONFIG["ollama"]
_SESSION = requests.Session()  # reuse keep-alive connections to the Ollama server


def _extra() -> dict:
    """Shared request extras: keep the model warm between calls and bound the
    context window. keep_alive avoids slow cold reloads; num_ctx prevents the
    excerpts from being silently truncated (and over-allocating the KV cache)."""
    extra: dict = {}
    ka = _OLLAMA.get("keep_alive")
    if ka not in (None, ""):
        extra["keep_alive"] = ka
    opts: dict = {}
    if _OLLAMA.get("num_ctx"):
        opts["num_ctx"] = int(_OLLAMA["num_ctx"])
    if _OLLAMA.get("num_predict") not in (None, ""):
        opts["num_predict"] = int(_OLLAMA["num_predict"])
    if opts:
        extra["options"] = opts
    return extra


def warm_model(model: Optional[str] = None) -> None:
    """Preload the model so the first real question doesn't pay a cold load.
    Sending an empty prompt to /api/generate just loads weights and returns."""
    model = model or pick_model()
    if not model:
        return
    try:
        t0 = time.monotonic()
        _SESSION.post(f"{_OLLAMA['url']}/api/generate",
                      json={"model": model, "prompt": "", "stream": False, **_extra()},
                      timeout=_OLLAMA["request_timeout"])
        log.info("Warmed model %s in %.1fs", model, time.monotonic() - t0)
    except Exception as e:
        log.warning("model warm-up failed: %s", e)


def _prompt(question: str, context: str) -> str:
    return (
        "You are a research assistant. Answer the user's question using ONLY the "
        "paper excerpts below. Each excerpt is prefixed with a number like [1]. "
        "When you use a fact from an excerpt, cite it inline with its number, e.g. "
        "[1] or [2]. Format your answer in Markdown. If the excerpts do not contain "
        "the answer, say so plainly.\n\n"
        f"=== PAPER EXCERPTS ===\n{context}\n\n=== QUESTION ===\n{question}"
    )


def list_models() -> list[str]:
    try:
        r = _SESSION.get(f"{_OLLAMA['url']}/api/tags", timeout=5)
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


def embed(texts: list, model: str) -> list:
    """Return an embedding vector per input text. Uses the batch /api/embed,
    falling back to the older per-text /api/embeddings if that 404s."""
    r = _SESSION.post(f"{_OLLAMA['url']}/api/embed",
                      json={"model": model, "input": texts},
                      timeout=_OLLAMA["request_timeout"])
    if r.status_code == 404:
        out = []
        for t in texts:
            rr = _SESSION.post(f"{_OLLAMA['url']}/api/embeddings",
                               json={"model": model, "prompt": t},
                               timeout=_OLLAMA["request_timeout"])
            rr.raise_for_status()
            out.append(rr.json()["embedding"])
        return out
    r.raise_for_status()
    return r.json()["embeddings"]


def expand_query(question: str, model: str, n: int = 3) -> list:
    """Ask the model for `n` alternative phrasings/synonym queries (one per line)."""
    prompt = (
        f"Generate {n} short alternative search queries (different wording and synonyms) "
        f"for the question below. Output one query per line, no numbering, no preamble.\n\n"
        f"Question: {question}"
    )
    r = _SESSION.post(f"{_OLLAMA['url']}/api/generate",
                      json={"model": model, "prompt": prompt, "stream": False},
                      timeout=_OLLAMA["request_timeout"])
    r.raise_for_status()
    text = r.json().get("response", "")
    out = []
    for line in text.splitlines():
        q = line.strip().lstrip("-*0123456789. ").strip()
        if q and q.lower() != question.lower():
            out.append(q)
    return out[:n]


def chat(question: str, context: str, model: str) -> str:
    log.info("Ollama chat: model=%s, context=%d chars, question=%r",
             model, len(context), question[:80])
    t0 = time.monotonic()
    r = _SESSION.post(
        f"{_OLLAMA['url']}/api/chat",
        json={"model": model, "messages": [{"role": "user", "content": _prompt(question, context)}],
              "stream": False, **_extra()},
        timeout=_OLLAMA["request_timeout"],
    )
    r.raise_for_status()
    answer = r.json()["message"]["content"].strip()
    log.info("Ollama answered in %.1fs (%d chars)", time.monotonic() - t0, len(answer))
    return answer


def verify_claims(answer: str, context: str, model: str) -> str:
    """Fact-check an answer against the source excerpts; return a short note."""
    prompt = (
        "You are a fact-checker. Given the SOURCES and an ANSWER, list any claims in the "
        "answer that are NOT supported by the sources, as short bullet points. If every claim "
        "is supported, reply with exactly: All claims supported.\n\n"
        f"SOURCES:\n{context}\n\nANSWER:\n{answer}"
    )
    r = _SESSION.post(
        f"{_OLLAMA['url']}/api/chat",
        json={"model": model, "messages": [{"role": "user", "content": prompt}],
              "stream": False, **_extra()},
        timeout=_OLLAMA["request_timeout"],
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def chat_stream(question: str, context: str, model: str) -> Iterator[str]:
    """Yield answer text chunks as Ollama generates them (stream=True)."""
    log.info("Ollama chat (stream): model=%s, context=%d chars, question=%r",
             model, len(context), question[:80])
    t0 = time.monotonic()
    with _SESSION.post(
        f"{_OLLAMA['url']}/api/chat",
        json={"model": model, "messages": [{"role": "user", "content": _prompt(question, context)}],
              "stream": True, **_extra()},
        stream=True,
        timeout=_OLLAMA["request_timeout"],
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            tok = (obj.get("message") or {}).get("content")
            if tok:
                yield tok
            if obj.get("done"):
                break
    log.info("Ollama stream finished in %.1fs", time.monotonic() - t0)
