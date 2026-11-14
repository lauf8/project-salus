from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b7a3d9210f65"
down_revision = "84312d70b449"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("revision", sa.Text(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_url", "revision", name="uq_knowledge_documents_source_revision"),
    )
    op.create_table(
        "knowledge_passages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("knowledge_documents.id"), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("topic_codes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.UniqueConstraint("document_id", "section", name="uq_knowledge_passages_document_section"),
    )
    op.create_index("ix_knowledge_passages_document_id", "knowledge_passages", ["document_id"])
    op.create_index("ix_knowledge_passages_topic_codes", "knowledge_passages", ["topic_codes"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_knowledge_passages_topic_codes", table_name="knowledge_passages")
    op.drop_index("ix_knowledge_passages_document_id", table_name="knowledge_passages")
    op.drop_table("knowledge_passages")
    op.drop_table("knowledge_documents")
