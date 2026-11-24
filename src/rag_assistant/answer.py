"""Answer field questions with a local Ollama model over retrieved guideline chunks.

Rules enforced here (master instruction A2.7 - no black boxes, no invention):

* only retrieved chunks are given to the model, and the prompt forbids outside facts;
* every answer carries document + page citations;
* if nothing relevant is retrieved the assistant says so instead of guessing;
* if Ollama is not running, the answer degrades to an extractive summary of the
  retrieved passages and says so explicitly.
"""

from __future__ import annotations

from typing import Any

import requests

from src.config.settings import ollama_settings
from src.rag_assistant.index import Retriever, SearchHit

MIN_SCORE = 0.05
CONTEXT_CHUNKS = 4

SYSTEM_PROMPT = (
    "You are an agricultural field assistant for a Karnataka Agriculture Officer. "
    "Answer ONLY from the numbered context passages. If the context does not contain "
    "the answer, reply exactly: 'The provided guidelines do not cover this.' "
    "Cite passages inline as [1], [2]. Keep the answer under 180 words and use short "
    "bullets for checklists. Never invent pesticide doses, scheme names or numbers."
)


def build_prompt(question: str, hits: list[SearchHit], context: dict[str, str] | None = None) -> str:
    """Compose the prompt from the retrieved passages plus optional village context."""
    passages = "\n\n".join(
        f"[{index}] ({hit.chunk.source_file}, page {hit.chunk.page})\n{hit.chunk.text}"
        for index, hit in enumerate(hits, start=1)
    )
    extra = ""
    if context:
        details = ", ".join(f"{key}={value}" for key, value in context.items() if value)
        extra = f"Village context (use it to tailor the checklist): {details}\n\n"
    return f"{SYSTEM_PROMPT}\n\n{extra}Context passages:\n{passages}\n\nQuestion: {question}\nAnswer:"


def ask_ollama(prompt: str, timeout: int = 90) -> str | None:
    """Send a prompt to the local Ollama server, returning None when it is unavailable."""
    base_url, model = ollama_settings()
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}},
            timeout=timeout,
        )
        response.raise_for_status()
        return str(response.json().get("response", "")).strip()
    except Exception:  # noqa: BLE001 - any transport/model error falls back safely
        return None


def _extractive_answer(hits: list[SearchHit]) -> str:
    """Fallback: quote the most relevant sentences from the retrieved passages."""
    bullets = []
    for index, hit in enumerate(hits, start=1):
        sentences = [s.strip() for s in hit.chunk.text.replace("\n", " ").split(". ") if len(s.strip()) > 40]
        snippet = "; ".join(sentences[:2]) if sentences else hit.chunk.text[:220]
        bullets.append(f"- [{index}] {snippet[:300]}")
    return (
        "Ollama is not reachable, so this is an extractive answer from the retrieved "
        "guidelines (no generation):\n" + "\n".join(bullets)
    )


def answer_question(
    question: str,
    context: dict[str, str] | None = None,
    retriever: Retriever | None = None,
    top_k: int = CONTEXT_CHUNKS,
) -> dict[str, Any]:
    """Retrieve, generate and return an answer with citations.

    Args:
        question: The officer's question.
        context: Optional village/crop/category context.
        retriever: Optional pre-built retriever (the Streamlit page caches one).
        top_k: Number of passages to retrieve.

    Returns:
        Dictionary with ``answer``, ``sources``, ``mode`` and ``hits``. ``answer`` may be
        a refusal message when retrieval finds nothing relevant.
    """
    retriever = retriever or Retriever()
    if not retriever.available:
        return {
            "answer": (
                "No guideline index is available. Add PDFs to guidelines_pdfs/ and run "
                "`python -m src.rag_assistant.ingest`, then retry."
            ),
            "sources": [],
            "mode": "unavailable",
            "hits": [],
        }

    hits = [hit for hit in retriever.search(question, top_k) if hit.score >= MIN_SCORE]
    if not hits:
        return {
            "answer": "The provided guidelines do not cover this. No relevant passage was retrieved.",
            "sources": [],
            "mode": retriever.mode,
            "hits": [],
        }

    prompt = build_prompt(question, hits, context)
    generated = ask_ollama(prompt)
    mode = f"{retriever.mode}+ollama"
    answer = generated
    if generated is None:
        mode = f"{retriever.mode}+extractive"
        answer = _extractive_answer(hits)

    sources = [
        {
            "citation": f"[{index}]",
            "document": hit.chunk.source_file,
            "title": hit.chunk.title,
            "page": hit.chunk.page,
            "score": round(hit.score, 3),
            "excerpt": hit.chunk.text[:400],
        }
        for index, hit in enumerate(hits, start=1)
    ]
    return {"answer": answer, "sources": sources, "mode": mode, "hits": hits}
