from alembic import op
import sqlalchemy as sa


revision = 'd15c6e7f8091'
down_revision = 'c04b5d6e7f80'
branch_labels = None
depends_on = None


CONTEXT_COLUMNS = [
    sa.Column('unit', sa.String(), nullable=True),
    sa.Column('original_values', sa.JSON(), nullable=True),
    sa.Column('activity', sa.String(), nullable=False, server_default='unknown'),
    sa.Column('supplemental_oxygen', sa.Boolean(), nullable=True),
    sa.Column('signal_quality', sa.String(), nullable=False, server_default='unknown'),
    sa.Column('glucose_context', sa.String(), nullable=False, server_default='unknown'),
    sa.Column('symptoms_status', sa.String(), nullable=False, server_default='unknown'),
    sa.Column('symptoms', sa.JSON(), nullable=False, server_default='[]'),
    sa.Column('acute_confusion', sa.Boolean(), nullable=True),
    sa.Column('client_request_id', sa.String(), nullable=True),
    sa.Column('submission_hash', sa.String(), nullable=True),
    sa.Column('evaluation_status', sa.String(), nullable=False, server_default='not_evaluated'),
    sa.Column('evaluation_notes', sa.JSON(), nullable=False, server_default='[]'),
    sa.Column('evaluation_profile', sa.JSON(), nullable=True),
]


CONTEXT_CHECKS = {
    'ck_health_activity': "activity IN ('rest','exercise','unknown')",
    'ck_health_signal_quality': "signal_quality IN ('good','poor','unknown')",
    'ck_health_glucose_context': "glucose_context IN ('fasting','after_meal','unknown')",
    'ck_health_symptoms_status': "symptoms_status IN ('present','absent','unknown')",
}


def upgrade():
    for column in CONTEXT_COLUMNS:
        op.add_column('health_observations', column)
    for name, condition in CONTEXT_CHECKS.items():
        op.create_check_constraint(name, 'health_observations', condition)
    op.create_unique_constraint('uq_health_observation_request', 'health_observations', ['astronaut_id', 'client_request_id'])
    op.create_unique_constraint('uq_health_observation_submission', 'health_observations', ['astronaut_id', 'submission_hash'])
    op.create_table('health_alert_settings',
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), primary_key=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('profile_id', sa.String(), nullable=False),
        sa.Column('timezone', sa.String(), nullable=False),
        sa.Column('emergency_channel', sa.String(), nullable=True),
        sa.Column('oxygen_thresholds', sa.JSON(), nullable=True),
        sa.Column('high_glucose_thresholds', sa.JSON(), nullable=False),
        sa.Column('approval_note', sa.Text(), nullable=True),
        sa.Column('approved_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table('health_alerts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('astronaut_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=True),
        sa.Column('rule_id', sa.String(), nullable=False),
        sa.Column('rule_version', sa.String(), nullable=False),
        sa.Column('profile_snapshot', sa.JSON(), nullable=False),
        sa.Column('indicator', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('verification_required', sa.Boolean(), nullable=False),
        sa.Column('trigger_observation_id', sa.Integer(), sa.ForeignKey('health_observations.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.CheckConstraint("severity IN ('attention','urgent','critical')", name='ck_health_alert_severity'),
        sa.CheckConstraint("status IN ('open','acknowledged','resolved')", name='ck_health_alert_status'),
    )
    op.create_index('ix_health_alerts_astronaut_id', 'health_alerts', ['astronaut_id'])
    op.create_index('uq_health_alert_active_rule', 'health_alerts', ['astronaut_id', 'rule_id'], unique=True, postgresql_where=sa.text("status IN ('open','acknowledged')"))
    op.create_table('health_alert_observations',
        sa.Column('alert_id', sa.Integer(), sa.ForeignKey('health_alerts.id'), primary_key=True),
        sa.Column('observation_id', sa.Integer(), sa.ForeignKey('health_observations.id'), primary_key=True),
    )
    op.create_table('health_alert_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('alert_id', sa.Integer(), sa.ForeignKey('health_alerts.id'), nullable=False),
        sa.Column('observation_id', sa.Integer(), sa.ForeignKey('health_observations.id'), nullable=True),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('rule_version', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_health_alert_events_alert_id', 'health_alert_events', ['alert_id'])


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text('SELECT EXISTS (SELECT 1 FROM health_alerts)')).scalar():
        raise RuntimeError('Exporte e preserve o histórico de alertas antes de reverter esta migration')
    for table in ('health_alert_events', 'health_alert_observations', 'health_alerts', 'health_alert_settings'):
        op.drop_table(table)
    op.drop_constraint('uq_health_observation_request', 'health_observations', type_='unique')
    op.drop_constraint('uq_health_observation_submission', 'health_observations', type_='unique')
    for name in CONTEXT_CHECKS:
        op.drop_constraint(name, 'health_observations', type_='check')
    for column in reversed(CONTEXT_COLUMNS):
        op.drop_column('health_observations', column.name)
