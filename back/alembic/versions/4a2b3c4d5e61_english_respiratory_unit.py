from alembic import op
from sqlalchemy import text


revision = '4a2b3c4d5e61'
down_revision = '3f1a2b4c5d60'
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().execute(text("UPDATE health_observations SET unit = 'breaths/min' WHERE indicator = 'respiratory_rate' AND unit = 'respirações/min'"))


def downgrade():
    op.get_bind().execute(text("UPDATE health_observations SET unit = 'respirações/min' WHERE indicator = 'respiratory_rate' AND unit = 'breaths/min'"))
