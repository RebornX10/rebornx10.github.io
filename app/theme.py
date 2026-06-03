from __future__ import annotations

from app.config import CONFIG
from app.models import Paper

SYSTEM = (
    "You are a scientific librarian. Given a paper's title and abstract, reply with "
    "a single concise research theme tag of 1-4 words. Reply with ONLY the tag."
)


def tag_theme(paper: Paper, client) -> Paper:
    basis = paper.abstract or (paper.content[:2000] if paper.content else "")
    if not paper.title and not basis:
        return paper
    msg = client.messages.create(
        model=CONFIG["theme"]["anthropic_model"],
        max_tokens=20,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Title: {paper.title}\n\nAbstract: {basis}"}],
    )
    paper.theme = msg.content[0].text.strip()
    return paper
