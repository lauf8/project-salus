from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel


class KnowledgeDocument(SQLModel, table=True):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("source_url", "revision", name="uq_knowledge_documents_source_revision"),
    )

    id: int | None = Field(default=None, primary_key=True)
    stable_id: str = Field(default_factory=lambda: uuid4().hex, unique=True)
    document_type: str = Field(default="reference", sa_type=Text)
    is_public: bool = False
    title: str = Field(sa_type=Text)
    source_url: str = Field(sa_type=Text)
    revision: str = Field(sa_type=Text)
    imported_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class KnowledgePassage(SQLModel, table=True):
    __tablename__ = "knowledge_passages"
    __table_args__ = (
        UniqueConstraint("document_id", "section", name="uq_knowledge_passages_document_section"),
        Index("ix_knowledge_passages_topic_codes", "topic_codes", postgresql_using="gin"),
    )

    id: int | None = Field(default=None, primary_key=True)
    stable_id: str = Field(default_factory=lambda: uuid4().hex, unique=True)
    document_id: int = Field(foreign_key="knowledge_documents.id", index=True)
    section: str = Field(sa_type=Text)
    page_number: int | None = None
    content: str = Field(sa_type=Text)
    topic_codes: list[str] = Field(sa_column=Column(ARRAY(Text), nullable=False))
