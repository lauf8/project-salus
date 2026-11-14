import sqlalchemy as sa
from alembic import op


revision = 'd7bc2345e6f7'
down_revision = 'c6ab1234d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('missions', sa.Column('crew_size', sa.Integer(), nullable=True))
    op.execute("UPDATE missions SET crew_size = (SELECT count(*) FROM mission_members WHERE mission_members.mission_id = missions.id AND mission_members.role = 'astronaut') WHERE EXISTS (SELECT 1 FROM mission_members WHERE mission_members.mission_id = missions.id AND mission_members.role = 'astronaut')")
    op.create_check_constraint('ck_missions_crew_size', 'missions', 'crew_size IS NULL OR crew_size > 0')


def downgrade():
    op.drop_constraint('ck_missions_crew_size', 'missions', type_='check')
    op.drop_column('missions', 'crew_size')
