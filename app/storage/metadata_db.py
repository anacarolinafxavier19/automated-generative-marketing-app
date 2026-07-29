"""Metadata store abstraction.

SQLite/SQLModel locally; swap for Cosmos DB / Azure Database for PostgreSQL
in the Azure target architecture -- callers only depend on the functions
below, not the table implementation.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.core.config import Settings


class DocumentRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    company_name: str = Field(index=True)
    role: str = Field(index=True)  # "sender" | "receiver"
    filename: str
    file_path: str
    chunk_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ImageAssetRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    document_id: str = Field(index=True)
    company_name: str = Field(index=True)
    role: str = Field(index=True)
    file_path: str
    page_number: int
    is_logo: bool = False


class GenerationMetricsRecord(SQLModel, table=True):
    """One row per /generate call — token usage, cost, latency, and constraint outcome.

    Feeds the /metrics endpoint (agentic-metrics dashboard + the app-evaluator agent).
    """

    id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    sender_company: str
    receiver_company: str
    receiver_source: str = "document"  # "document" (uploaded PDF) | "web_research" (no PDF, live search)
    model_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_seconds: float
    repair_pass_needed: bool
    initial_violations_count: int
    final_violations_count: int
    sender_chunks_used: int
    receiver_chunks_used: int
    cost_usd: float
    cost_eur: float


class MetadataStore:
    def __init__(self, settings: Settings):
        self._engine = create_engine(f"sqlite:///{settings.metadata_db_path}")
        SQLModel.metadata.create_all(self._engine)

    def add_document(self, record: DocumentRecord) -> None:
        with Session(self._engine) as session:
            session.add(record)
            session.commit()

    def add_image(self, record: ImageAssetRecord) -> None:
        with Session(self._engine) as session:
            session.add(record)
            session.commit()

    def list_documents(self, company_name: str, role: Optional[str] = None) -> list[DocumentRecord]:
        with Session(self._engine) as session:
            stmt = select(DocumentRecord).where(DocumentRecord.company_name == company_name)
            if role:
                stmt = stmt.where(DocumentRecord.role == role)
            return list(session.exec(stmt))

    def list_images(self, company_name: str, role: str) -> list[ImageAssetRecord]:
        with Session(self._engine) as session:
            stmt = select(ImageAssetRecord).where(
                ImageAssetRecord.company_name == company_name,
                ImageAssetRecord.role == role,
            )
            return list(session.exec(stmt))

    def get_logo(self, company_name: str, role: str) -> Optional[ImageAssetRecord]:
        with Session(self._engine) as session:
            stmt = select(ImageAssetRecord).where(
                ImageAssetRecord.company_name == company_name,
                ImageAssetRecord.role == role,
                ImageAssetRecord.is_logo == True,  # noqa: E712
            )
            return session.exec(stmt).first()

    def add_generation_metrics(self, record: GenerationMetricsRecord) -> None:
        with Session(self._engine) as session:
            session.add(record)
            session.commit()

    def list_generation_metrics(self, limit: int = 500) -> list[GenerationMetricsRecord]:
        with Session(self._engine) as session:
            stmt = select(GenerationMetricsRecord).order_by(GenerationMetricsRecord.created_at.desc()).limit(limit)
            return list(session.exec(stmt))
