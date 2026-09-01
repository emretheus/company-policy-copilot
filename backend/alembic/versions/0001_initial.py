"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-31

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("email", sa.String, nullable=False, unique=True),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("department", sa.String, nullable=False),
        sa.Column("country", sa.String, nullable=False),
        sa.Column("manager_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
    )

    op.create_table(
        "document_families",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("title_base", sa.String, nullable=False),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("document_families.id"), nullable=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("version_label", sa.String, nullable=True),
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("country", sa.String, nullable=True),
        sa.Column("source_type", sa.String, nullable=False, server_default="seed"),
        sa.Column("source_uri", sa.String, nullable=True),
        sa.Column("content_hash", sa.String, nullable=True),
        sa.Column("ingested_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "document_access_rules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("rule_json", postgresql.JSONB, nullable=False),
    )

    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("chunk_index", sa.Integer, nullable=False, server_default="0"),
    )
    op.execute(
        "CREATE INDEX chunks_embedding_idx ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "ALTER TABLE chunks ADD COLUMN text_search tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', text)) STORED"
    )
    op.execute("CREATE INDEX chunks_text_search_idx ON chunks USING gin (text_search)")

    op.create_table(
        "document_relations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("from_document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("to_document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("relation_type", sa.String, nullable=False),
    )

    op.create_table(
        "query_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("filter_applied_json", postgresql.JSONB, nullable=True),
        sa.Column("retrieved_chunk_ids", postgresql.JSONB, nullable=True),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column("abstained", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("verifier_result_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("query_log")
    op.drop_table("document_relations")
    op.drop_index("chunks_text_search_idx", table_name="chunks")
    op.drop_index("chunks_embedding_idx", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("document_access_rules")
    op.drop_table("documents")
    op.drop_table("document_families")
    op.drop_table("users")
