"""Build a FAISS / TF-IDF retrieval index over the guideline chunks.

Two modes, chosen by what is installed:

``faiss``
    Sentence-Transformer embeddings + FAISS inner-product index (the target stack:
    Sentence Transformers + FAISS).

``tfidf``
    scikit-learn TF-IDF + cosine similarity. Used when the sentence-transformers and
    faiss packages are not installed, so the assistant still runs on a normal laptop.
    The mode is always reported in the UI so retrieval quality is never overstated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from src.config.settings import project_path
from src.rag_assistant.ingest import Chunk, load_chunks

INDEX_DIR = project_path("src", "rag_assistant", "index")
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class SearchHit:
    """A retrieved chunk with its similarity score."""

    chunk: Chunk
    score: float


def _try_sentence_transformers(chunks: list[Chunk]) -> tuple[str, Any] | None:
    """Embed chunks with Sentence Transformers + FAISS, or return None if unavailable."""
    try:
        import faiss  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ModuleNotFoundError:
        return None
    model = SentenceTransformer(EMBEDDING_MODEL)
    vectors = model.encode([chunk.text for chunk in chunks], normalize_embeddings=True)
    vectors = np.asarray(vectors, dtype="float32")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    return "faiss", (model, index, vectors)


def _try_tfidf(chunks: list[Chunk]) -> tuple[str, Any] | None:
    """Build a TF-IDF index, or return None if scikit-learn is unavailable."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ModuleNotFoundError:
        return None
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform([chunk.text for chunk in chunks])
    return "tfidf", (vectorizer, matrix)


class Retriever:
    """Loads the chunk corpus once and answers similarity queries."""

    def __init__(self, chunks: list[Chunk] | None = None, mode: str = "auto") -> None:
        self.chunks: list[Chunk] = chunks or load_chunks()
        self.mode = "none"
        self._backend: Any = None
        if not self.chunks:
            return
        if mode in ("auto", "faiss"):
            built = _try_sentence_transformers(self.chunks)
            if built:
                self.mode, self._backend = built
                return
        if mode in ("auto", "tfidf"):
            built = _try_tfidf(self.chunks)
            if built:
                self.mode, self._backend = built

    @property
    def available(self) -> bool:
        return self.mode != "none"

    def search(self, question: str, top_k: int = 4) -> list[SearchHit]:
        """Return the ``top_k`` most similar chunks with scores."""
        if not self.available or not question.strip():
            return []
        if self.mode == "faiss":
            model, index, _ = self._backend
            query = np.asarray(model.encode([question], normalize_embeddings=True), dtype="float32")
            scores, ids = index.search(query, min(top_k, len(self.chunks)))
            return [
                SearchHit(chunk=self.chunks[int(i)], score=float(s))
                for s, i in zip(scores[0], ids[0])
                if i >= 0
            ]
        vectorizer, matrix = self._backend
        from sklearn.metrics.pairwise import cosine_similarity

        query_vector = vectorizer.transform([question])
        scores = cosine_similarity(query_vector, matrix)[0]
        order = np.argsort(scores)[::-1][:top_k]
        return [SearchHit(chunk=self.chunks[int(i)], score=float(scores[i])) for i in order if scores[i] > 0]


def index_status() -> dict[str, Any]:
    """Return a summary of the retrieval configuration (used by the UI/docs)."""
    retriever = Retriever()
    return {
        "mode": retriever.mode,
        "chunks": len(retriever.chunks),
        "documents": sorted({chunk.source_file for chunk in retriever.chunks}),
        "embedding_model": EMBEDDING_MODEL if retriever.mode == "faiss" else "tf-idf (fallback)",
    }


if __name__ == "__main__":
    status = index_status()
    print("Retrieval index status:")
    for key, value in status.items():
        print(f"  {key}: {value}")
