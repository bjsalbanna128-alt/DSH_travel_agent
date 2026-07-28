"""Local embedding provider using sentence-transformers with bge-small-zh-v1.5."""

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_embedding_instance: Optional["LocalEmbeddingProvider"] = None


class LocalEmbeddingProvider:
    """Singleton wrapper around sentence-transformers for local embeddings.

    Uses BAAI/bge-small-zh-v1.5 (512-dim, ~24M params) — fast CPU inference.
    """

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.embedding_model_name
        self._model = None
        # Use HF mirror for China access
        import os
        if not os.environ.get("HF_ENDPOINT"):
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            dim = self._model.get_sentence_embedding_dimension()
            logger.info(f"Embedding model loaded (dim={dim})")
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of float vectors."""
        if not texts:
            return []
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query text."""
        return self.embed([text])[0]

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()


_reranker_instance: Optional["CrossEncoderReranker"] = None


class CrossEncoderReranker:
    """Cross-Encoder re-ranker using bge-reranker-v2-m3.

    Unlike bi-encoders (which encode query and doc separately), a cross-encoder
    processes (query, doc) jointly, producing much more accurate relevance scores.
    Used as a second-pass re-ranker on top-K candidates from the embedding search.
    """

    MODEL_NAME = "BAAI/bge-reranker-v2-m3"

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or self.MODEL_NAME
        self._model = None
        import os
        if not os.environ.get("HF_ENDPOINT"):
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading reranker model: {self.model_name}")
            self._model = CrossEncoder(self.model_name)
            logger.info("Reranker model loaded")
        return self._model

    def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[tuple[int, float]]:
        """Re-rank documents by relevance to query.

        Returns list of (original_index, score) sorted by score descending.
        If top_k is None, returns all results.
        """
        if not documents:
            return []

        pairs = [(query, doc) for doc in documents]
        scores = self.model.predict(pairs, show_progress_bar=False)

        # scores is a list of floats; pair with original indices
        indexed = [(i, float(s)) for i, s in enumerate(scores)]
        indexed.sort(key=lambda x: x[1], reverse=True)

        if top_k is not None:
            indexed = indexed[:top_k]

        return indexed


def get_reranker() -> CrossEncoderReranker:
    """Get or create the singleton re-ranker."""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = CrossEncoderReranker()
    return _reranker_instance


def get_embedding_provider() -> LocalEmbeddingProvider:
    """Get or create the singleton embedding provider."""
    global _embedding_instance
    if _embedding_instance is None:
        _embedding_instance = LocalEmbeddingProvider()
    return _embedding_instance
