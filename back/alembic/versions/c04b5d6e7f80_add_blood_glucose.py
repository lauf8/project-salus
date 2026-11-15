from alembic import op
from sqlalchemy import text


revision = 'c04b5d6e7f80'
down_revision = 'b93a4c5d6e7f'
branch_labels = None
depends_on = None


PREVIOUS_INDICATORS = "'heart_rate','blood_pressure','respiratory_rate','oxygen_saturation','body_temperature','consciousness','sleep_duration','sleep_quality','fatigue','mood','attention'"


def upgrade():
    op.drop_constraint('ck_health_indicator', 'health_observations', type_='check')
    op.create_check_constraint('ck_health_indicator', 'health_observations', f"indicator IN ({PREVIOUS_INDICATORS},'blood_glucose')")
    op.create_check_constraint('ck_health_glucose_positive', 'health_observations', "indicator != 'blood_glucose' OR value > 0")


def downgrade():
    connection = op.get_bind()
    if connection.execute(text("SELECT EXISTS (SELECT 1 FROM health_observations WHERE indicator = 'blood_glucose')")).scalar():
        raise RuntimeError('The migration cannot be reverted while blood glucose records exist')
    op.drop_constraint('ck_health_glucose_positive', 'health_observations', type_='check')
    op.drop_constraint('ck_health_indicator', 'health_observations', type_='check')
    op.create_check_constraint('ck_health_indicator', 'health_observations', f'indicator IN ({PREVIOUS_INDICATORS})')
