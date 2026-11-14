"""Fluxo de radiação: alertas próprios, relatos de sintomas e ajustes no acompanhamento.

- radiation_alerts: alertas sem medição de origem (evento, acompanhamento ou dose).
- radiation_symptom_reports: relatos de sintomas na janela de 48 h.
- radiation_follow_ups.detected_at e opened_by_user_id opcional (sincronização agendada).
"""

from alembic import op
import sqlalchemy as sa


revision = '0b7c1d2e3f40'
down_revision = 'a0ef5678b920'
branch_labels = None
depends_on = None


RULES = "'sep_during_eva', 'proton_flux_during_eva', 'prodromal_vomiting', 'prodromal_symptoms', 'skin_reaction', 'late_symptoms', 'dose_limit'"


def _timestamp(name, nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade():
    op.add_column('radiation_follow_ups', _timestamp('detected_at', True))
    op.execute('UPDATE radiation_follow_ups SET detected_at = opened_at')
    op.alter_column('radiation_follow_ups', 'detected_at', nullable=False)
    op.alter_column('radiation_follow_ups', 'opened_by_user_id', existing_type=sa.Integer(), nullable=True)

    op.create_table('radiation_symptom_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('follow_up_id', sa.Integer(), sa.ForeignKey('radiation_follow_ups.id', ondelete='CASCADE'), nullable=False),
        _timestamp('reported_at'),
        sa.Column('symptoms', sa.JSON(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('observation_id', sa.Integer(), sa.ForeignKey('health_observations.id'), nullable=True),
        sa.Column('recorded_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        _timestamp('recorded_at'),
    )
    op.create_index('ix_radiation_symptom_report_follow_up', 'radiation_symptom_reports', ['follow_up_id', 'reported_at'])

    op.create_table('radiation_alerts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=False),
        sa.Column('astronaut_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('rule_id', sa.String(), nullable=False),
        sa.Column('dedupe_key', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('space_weather_events.id'), nullable=True),
        sa.Column('follow_up_id', sa.Integer(), sa.ForeignKey('radiation_follow_ups.id', ondelete='SET NULL'), nullable=True),
        sa.Column('dose_record_id', sa.Integer(), sa.ForeignKey('radiation_dose_records.id', ondelete='SET NULL'), nullable=True),
        sa.Column('details', sa.JSON(), nullable=False),
        _timestamp('created_at'),
        _timestamp('updated_at'),
        _timestamp('acknowledged_at', True),
        sa.Column('acknowledged_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        _timestamp('resolved_at', True),
        sa.Column('resolved_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.CheckConstraint("severity IN ('attention', 'urgent', 'critical')", name='ck_radiation_alert_severity'),
        sa.CheckConstraint("status IN ('open', 'acknowledged', 'resolved')", name='ck_radiation_alert_status'),
        sa.CheckConstraint(f'rule_id IN ({RULES})', name='ck_radiation_alert_rule'),
    )
    op.create_index('ix_radiation_alerts_astronaut_id', 'radiation_alerts', ['astronaut_id'])
    op.create_index('ix_radiation_alert_mission', 'radiation_alerts', ['mission_id', 'status', 'updated_at'])
    op.create_index(
        'uq_radiation_alert_active', 'radiation_alerts', ['astronaut_id', 'dedupe_key'], unique=True,
        postgresql_where=sa.text("status IN ('open', 'acknowledged')"),
    )


def downgrade():
    connection = op.get_bind()
    for table in ('radiation_alerts', 'radiation_symptom_reports'):
        if connection.execute(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table})')).scalar():
            raise RuntimeError(f'Preserve os registros de {table} antes de reverter esta migration')
    if connection.execute(sa.text('SELECT EXISTS (SELECT 1 FROM radiation_follow_ups WHERE opened_by_user_id IS NULL)')).scalar():
        raise RuntimeError('Há acompanhamentos abertos pela sincronização agendada; atribua um usuário antes de reverter')
    op.drop_table('radiation_alerts')
    op.drop_table('radiation_symptom_reports')
    op.alter_column('radiation_follow_ups', 'opened_by_user_id', existing_type=sa.Integer(), nullable=False)
    op.drop_column('radiation_follow_ups', 'detected_at')
