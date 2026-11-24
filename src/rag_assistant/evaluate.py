"""Small, honest retrieval evaluation for the field assistant.

The evaluation only measures *retrieval* (did the right passage come back?), not answer
quality, and it runs against whatever corpus is present. With the committed demo note the
numbers describe the demo note, not official guidelines - that is stated in
``docs/rag_evaluation.md``.
"""

from __future__ import annotations

from typing import Any

from src.rag_assistant.answer import answer_question
from src.rag_assistant.index import Retriever

#: (question, keyword that must appear in a retrieved passage)
TEST_CASES: list[tuple[str, str]] = [
    ("What should I check first in a paddy field with planthopper hoppers?", "hopper"),
    ("How do I confirm drought stress in a ragi field?", "drought"),
    ("Which symptoms suggest blast disease in paddy?", "blast"),
    ("What is the inspection checklist for a waterlogged sugarcane field?", "waterlog"),
    ("What should the officer ask the farmer about affected area?", "area"),
]


def evaluate(top_k: int = 4) -> dict[str, Any]:
    """Run the test questions and report retrieval hit rate and mode."""
    retriever = Retriever()
    rows = []
    for question, keyword in TEST_CASES:
        hits = retriever.search(question, top_k)
        top_text = " ".join(hit.chunk.text.lower() for hit in hits)
        rows.append(
            {
                "question": question,
                "expected_keyword": keyword,
                "hit": keyword.lower() in top_text,
                "top_score": round(hits[0].score, 3) if hits else 0.0,
                "top_document": hits[0].chunk.source_file if hits else "",
                "top_page": hits[0].chunk.page if hits else 0,
            }
        )
    hit_rate = sum(row["hit"] for row in rows) / len(rows) if rows else 0.0
    return {"rows": rows, "hit_rate": round(hit_rate, 3), "mode": retriever.mode, "corpus_size": len(retriever.chunks)}


def main() -> None:
    """CLI: print the evaluation table and one example answer."""
    report = evaluate()
    print(f"Retrieval mode: {report['mode']} | chunks: {report['corpus_size']}")
    for row in report["rows"]:
        status = "HIT " if row["hit"] else "MISS"
        print(f"  {status} {row['top_score']:.3f}  {row['top_document']} p{row['top_page']}  <- {row['question']}")
    print(f"\nRetrieval hit rate: {report['hit_rate'] * 100:.0f}% (retrieval only, not answer quality)\n")
    example = answer_question("What should I check first in a paddy field with planthopper hoppers?")
    print(f"Example answer ({example['mode']}):\n{example['answer']}")


if __name__ == "__main__":
    main()
