"""Vector store abstraction.

Chroma (persisted locally) for the prototype; swap for Azure AI Search
(hybrid vector + keyword index) in the Azure target architecture -- callers
only depend on `add_chunks()` / `query()`.
"""

import uuid
from typing import Protocol

from app.core.config import Settings
from app.retrieval.embeddings import EmbeddingClient


class VectorStore(Protocol):
    def add_chunks(self, company: str, role: str, document_id: str, chunks: list[str]) -> None: ...

    def query(self, company: str, role: str, query_text: str, top_k: int) -> list[str]: ...


class ChromaVectorStore:
    _COLLECTION = "context_chunks"

    def __init__(self, settings: Settings, embedding_client: EmbeddingClient):
        import chromadb

        self._embedding_client = embedding_client
        self._client = chromadb.PersistentClient(path=str(settings.vector_store_path))
        self._collection = self._client.get_or_create_collection(self._COLLECTION)

    def add_chunks(self, company: str, role: str, document_id: str, chunks: list[str]) -> None:
        if not chunks:
            return
        embeddings = self._embedding_client.embed(chunks)
        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [{"company_name": company, "role": role, "document_id": document_id} for _ in chunks]
        self._collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

    def query(self, company: str, role: str, query_text: str, top_k: int) -> list[str]:
        [query_embedding] = self._embedding_client.embed([query_text])
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"$and": [{"company_name": company}, {"role": role}]},
        )
        documents = results.get("documents") or [[]]
        return documents[0]
