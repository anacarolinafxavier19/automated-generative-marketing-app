"""Embedding client abstraction.

Local sentence-transformers model for the prototype (no API key needed);
swap for an Azure OpenAI embeddings deployment in the Azure target
architecture -- callers only depend on `embed()`.
"""

from typing import Protocol


class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalEmbeddingClient:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()
