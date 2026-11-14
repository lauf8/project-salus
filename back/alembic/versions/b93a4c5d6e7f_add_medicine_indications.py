from alembic import op
import sqlalchemy as sa


revision = 'b93a4c5d6e7f'
down_revision = 'a8293b4c5d6e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('medicines', sa.Column('main_indications', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('medicines', 'main_indications')
