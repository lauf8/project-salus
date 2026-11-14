from alembic import op
import sqlalchemy as sa

revision = "c4e5f6071829"
down_revision = "b7a3d9210f65"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("stable_id", sa.String(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("document_type", sa.Text(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("is_public", sa.Boolean(), nullable=True))
    op.add_column("knowledge_passages", sa.Column("stable_id", sa.String(), nullable=True))
    op.execute("""
        UPDATE knowledge_documents
        SET stable_id = md5(source_url || chr(31) || revision),
            document_type = CASE
                WHEN source_url LIKE 'https://www.nasa.gov/%/ochmo-tb-%' THEN 'technical_brief'
                WHEN source_url = 'https://humanresearchroadmap.nasa.gov/Risks/risk.aspx?i=105'
                    THEN 'risk_summary'
                ELSE 'reference'
            END,
            is_public = source_url IN (
                'https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf',
                'https://humanresearchroadmap.nasa.gov/Risks/risk.aspx?i=105'
            )
    """)
    op.execute("""
        UPDATE knowledge_passages AS passage
        SET stable_id = md5(document.stable_id || chr(31) || passage.section)
        FROM knowledge_documents AS document
        WHERE passage.document_id = document.id
    """)
    op.alter_column("knowledge_documents", "stable_id", nullable=False)
    op.alter_column("knowledge_documents", "document_type", nullable=False)
    op.alter_column("knowledge_documents", "is_public", nullable=False)
    op.alter_column("knowledge_passages", "stable_id", nullable=False)
    op.create_unique_constraint("uq_knowledge_documents_stable_id", "knowledge_documents", ["stable_id"])
    op.create_unique_constraint("uq_knowledge_passages_stable_id", "knowledge_passages", ["stable_id"])


def downgrade() -> None:
    op.drop_constraint("uq_knowledge_passages_stable_id", "knowledge_passages", type_="unique")
    op.drop_constraint("uq_knowledge_documents_stable_id", "knowledge_documents", type_="unique")
    op.drop_column("knowledge_passages", "stable_id")
    op.drop_column("knowledge_documents", "is_public")
    op.drop_column("knowledge_documents", "document_type")
    op.drop_column("knowledge_documents", "stable_id")
