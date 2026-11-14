import sqlalchemy as sa
from alembic import op


revision = 'b59a0123c4d5'
down_revision = 'a48f9012b3c4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('spacecraft', sa.Column('maximum_crew_capacity', sa.Integer(), nullable=True))
    op.create_check_constraint('ck_spacecraft_capacity', 'spacecraft', 'maximum_crew_capacity > 0')


def downgrade():
    op.drop_constraint('ck_spacecraft_capacity', 'spacecraft', type_='check')
    op.drop_column('spacecraft', 'maximum_crew_capacity')
