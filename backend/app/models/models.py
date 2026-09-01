import uuid
from datetime import datetime, date

from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db.session import Base
from app.config import settings


def uid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # Employee, Manager, HR, Finance Admin, Legal
    department: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)
    manager_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True
    )


class DocumentFamily(Base):
    __tablename__ = "document_families"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uid)
    title_base: Mapped[str] = mapped_column(String, nullable=False)

    documents: Mapped[list["Document"]] = relationship(back_populates="family")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uid)
    family_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("document_families.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    version_label: Mapped[str | None] = mapped_column(String, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id"), nullable=True
    )
    country: Mapped[str | None] = mapped_column(String, nullable=True)  # null = global
    source_type: Mapped[str] = mapped_column(String, default="seed")
    source_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    family: Mapped[DocumentFamily | None] = relationship(back_populates="documents")
    access_rules: Mapped[list["DocumentAccessRule"]] = relationship(back_populates="document")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document")


class DocumentAccessRule(Base):
    """
    A rule is a small JSON predicate evaluated against the requesting user.
    Examples:
      {"scope": "all"}
      {"scope": "department", "department": "HR"}
      {"scope": "department_or_role", "department": "Finance", "role": "Manager"}
      {"scope": "owner_manager_hr"}   -- owner, their manager, or HR (performance docs)
    """

    __tablename__ = "document_access_rules"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("documents.id"))
    rule_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    document: Mapped[Document] = relationship(back_populates="access_rules")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("documents.id"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)

    document: Mapped[Document] = relationship(back_populates="chunks")


class DocumentRelation(Base):
    """Graph edges beyond `supersedes` (which lives on Document directly)."""

    __tablename__ = "document_relations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uid)
    from_document_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("documents.id"))
    to_document_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("documents.id"))
    relation_type: Mapped[str] = mapped_column(String, nullable=False)  # relates_to | localizes


class QueryLog(Base):
    __tablename__ = "query_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    filter_applied_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    retrieved_chunk_ids: Mapped[dict] = mapped_column(JSON, nullable=True)  # list stored as JSON
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstained: Mapped[bool] = mapped_column(Boolean, default=False)
    verifier_result_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
