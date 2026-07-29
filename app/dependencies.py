"""Singleton wiring for the swappable interfaces.

Kept in one place so swapping an implementation (e.g. Chroma -> Azure AI
Search) is a one-line change here, not a hunt through the codebase.
"""
from functools import lru_cache

from fastapi import HTTPException
from langchain_community.vectorstores import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langsmith import Client as LangSmithClient

from app.core.config import get_settings
from app.generation.research import CompanyResearchClient
from app.storage.file_store import FileStore, LocalFileStore
from app.storage.metadata_db import MetadataStore


@lru_cache
def get_file_store() -> FileStore:
    # This remains as-is, since it deals with local file system storage.
    return LocalFileStore(get_settings())


@lru_cache
def get_metadata_store() -> MetadataStore:
    # This also remains, managing structured data in SQLite.
    return MetadataStore(get_settings())


@lru_cache
def get_embedding_client() -> GoogleGenerativeAIEmbeddings:
    settings = get_settings()
    if not settings.gemini_api_key:
        # Embeddings also require the API key
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured.")
    return GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=settings.gemini_api_key)


@lru_cache
def get_vector_store() -> Chroma:
    settings = get_settings()
    return Chroma(
        persist_directory=str(settings.vector_store_path),
        embedding_function=get_embedding_client(),
    )


@lru_cache
def get_llm_client() -> ChatGoogleGenerativeAI:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured. Set it in .env to enable article generation.",
        )
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        convert_system_message_to_human=True,  # Recommended for Gemini
    )


@lru_cache
def get_langsmith_client() -> LangSmithClient | None:
    if get_settings().langchain_tracing_v2:
        return LangSmithClient()
    return None


@lru_cache
def get_research_client() -> CompanyResearchClient:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured. Set it in .env to enable receiver company research.",
        )
    return CompanyResearchClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        tavily_api_key=settings.tavily_api_key or None,
    )
