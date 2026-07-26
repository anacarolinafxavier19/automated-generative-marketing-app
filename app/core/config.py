from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"

    storage_root: Path = Path("./storage")
    vector_store_path: Path = Path("./storage/vector_store")
    metadata_db_path: Path = Path("./storage/metadata.db")

    embedding_model: str = "all-MiniLM-L6-v2"
    retrieval_top_k: int = 6

    langchain_tracing_v2: bool = False

    def ensure_dirs(self) -> None:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.vector_store_path.mkdir(parents=True, exist_ok=True)
        (self.storage_root / "documents").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
