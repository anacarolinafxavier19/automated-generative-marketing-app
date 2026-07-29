from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-lite-latest"

    # Optional: free-tier fallback for receiver research when Gemini's Google Search
    # grounding quota (separate and much stricter than plain generation) is exhausted.
    # Sign up at https://app.tavily.com — no credit card required. Leave unset to keep
    # the original behavior (a 502 pointing at the receiver-PDF-upload workaround).
    tavily_api_key: str = ""

    storage_root: Path = Path("./storage")
    vector_store_path: Path = Path("./storage/vector_store")
    metadata_db_path: Path = Path("./storage/metadata.db")

    embedding_model: str = "all-MiniLM-L6-v2"
    retrieval_top_k: int = 6

    langchain_tracing_v2: bool = False

    # Pricing for cost estimation on /metrics — approximate, verified against public
    # pricing pages as of 2026-07-29 for gemini-flash-lite-latest (currently the
    # Gemini 2.5 Flash-Lite tier: $0.10 / $0.40 per 1M input/output tokens). Google is
    # retiring 2.5 Flash-Lite on 2026-10-16 in favor of 3.1 Flash-Lite ($0.25 / $1.50
    # per 1M tokens) — update these when that rolls out, or cost figures will silently
    # under-report. Same for the USD->EUR rate: a snapshot, not a live feed.
    gemini_input_price_usd_per_million: float = 0.10
    gemini_output_price_usd_per_million: float = 0.40
    usd_to_eur_rate: float = 0.88

    def ensure_dirs(self) -> None:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.vector_store_path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
