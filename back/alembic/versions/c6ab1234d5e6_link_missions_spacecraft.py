import sqlalchemy as sa
from alembic import op


revision = 'c6ab1234d5e6'
down_revision = 'b59a0123c4d5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('spacecraft', sa.Column('status', sa.String(), nullable=False, server_default='available'))
    op.add_column('missions', sa.Column('status', sa.String(), nullable=False, server_default='planned'))
    op.add_column('missions', sa.Column('spacecraft_id', sa.Integer(), nullable=True))
    op.create_check_constraint('ck_missions_status', 'missions', "status IN ('planned', 'in_progress', 'completed')")
    op.create_check_constraint('ck_spacecraft_status', 'spacecraft', "status IN ('available', 'in_use')")
    op.create_foreign_key('fk_missions_spacecraft', 'missions', 'spacecraft', ['spacecraft_id'], ['id'])
    op.create_index('ix_missions_spacecraft_id', 'missions', ['spacecraft_id'])
    op.execute("UPDATE missions SET status = CASE WHEN ended_at IS NOT NULL THEN 'completed' WHEN started_at IS NOT NULL THEN 'in_progress' ELSE 'planned' END")
    op.execute("UPDATE spacecraft SET status = 'in_use' WHERE id IN (SELECT spacecraft_id FROM missions WHERE status != 'completed' AND spacecraft_id IS NOT NULL)")
    op.create_index('uq_missions_open_spacecraft', 'missions', ['spacecraft_id'], unique=True, postgresql_where=sa.text("status != 'completed' AND spacecraft_id IS NOT NULL"))


def downgrade():
    op.drop_index('uq_missions_open_spacecraft', table_name='missions')
    op.drop_index('ix_missions_spacecraft_id', table_name='missions')
    op.drop_constraint('fk_missions_spacecraft', 'missions', type_='foreignkey')
    op.drop_constraint('ck_missions_status', 'missions', type_='check')
    op.drop_constraint('ck_spacecraft_status', 'spacecraft', type_='check')
    op.drop_column('missions', 'spacecraft_id')
    op.drop_column('missions', 'status')
    op.drop_column('spacecraft', 'status')
