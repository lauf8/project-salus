"""Clima espacial (NASA DONKI) e exposição à radiação.

Cria eventos FLR/CME/SEP e suas ligações, histórico de sincronizações, fluxo de
prótons, atividade da tripulação (IVA/EVA/abrigo), limites de dose, registros de
dose e acompanhamento pós-evento. Carrega o perfil de limites da Tabela 5-1 do
NASA SP-2009-3405.
"""

from alembic import op
import sqlalchemy as sa


revision = 'f9a1b2c3d4e5'
down_revision = 'f9de4567a819'
branch_labels = None
depends_on = None


ORGANS = "'lens', 'skin', 'bfo', 'heart', 'cns', 'cns_z_ge_10'"
TYPES = "'FLR', 'CME', 'SEP'"
LIMIT_PROFILE = 'nasa-sp-2009-3405-table-5-1'
LIMIT_SOURCE = 'NASA SP-2009-3405 (2009), cap. 5, Tabela 5-1. Valores históricos; confira o NASA-STD-3001 vigente.'
TABLE_5_1 = [
    ('lens', '30_day', 1000, 'mGy-Eq'), ('lens', '1_year', 2000, 'mGy-Eq'), ('lens', 'career', 4000, 'mGy-Eq'),
    ('skin', '30_day', 1500, 'mGy-Eq'), ('skin', '1_year', 3000, 'mGy-Eq'), ('skin', 'career', 6000, 'mGy-Eq'),
    ('bfo', '30_day', 250, 'mGy-Eq'), ('bfo', '1_year', 500, 'mGy-Eq'),
    ('heart', '30_day', 250, 'mGy-Eq'), ('heart', '1_year', 500, 'mGy-Eq'), ('heart', 'career', 1000, 'mGy-Eq'),
    ('cns', '30_day', 500, 'mGy-Eq'), ('cns', '1_year', 1000, 'mGy-Eq'), ('cns', 'career', 1500, 'mGy-Eq'),
    ('cns_z_ge_10', '1_year', 100, 'mGy'), ('cns_z_ge_10', 'career', 250, 'mGy'),
]
TABLES = (
    'radiation_follow_ups', 'radiation_dose_records', 'radiation_exposure_limits', 'crew_activities',
    'proton_flux_readings', 'space_weather_sync_runs', 'space_weather_event_links', 'space_weather_events',
)


def _timestamp(name, nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade():
    op.create_table('space_weather_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('activity_id', sa.Text(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('catalog', sa.Text(), nullable=True),
        _timestamp('start_time'),
        _timestamp('peak_time', True),
        _timestamp('end_time', True),
        sa.Column('source_location', sa.Text(), nullable=True),
        sa.Column('active_region_num', sa.Integer(), nullable=True),
        sa.Column('flare_class', sa.Text(), nullable=True),
        sa.Column('flare_peak_flux_wm2', sa.Float(), nullable=True),
        sa.Column('cme_speed_kms', sa.Float(), nullable=True),
        sa.Column('cme_half_angle_deg', sa.Float(), nullable=True),
        sa.Column('cme_type', sa.Text(), nullable=True),
        sa.Column('cme_latitude', sa.Float(), nullable=True),
        sa.Column('cme_longitude', sa.Float(), nullable=True),
        _timestamp('cme_time_21_5', True),
        sa.Column('instruments', sa.JSON(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('link', sa.Text(), nullable=True),
        sa.Column('version_id', sa.Integer(), nullable=True),
        _timestamp('submission_time', True),
        sa.Column('raw', sa.JSON(), nullable=False),
        _timestamp('first_seen_at'),
        _timestamp('last_synced_at'),
        sa.CheckConstraint(f'event_type IN ({TYPES})', name='ck_space_weather_event_type'),
        sa.CheckConstraint('length(trim(activity_id)) > 0', name='ck_space_weather_activity_id'),
        sa.CheckConstraint('end_time IS NULL OR end_time >= start_time', name='ck_space_weather_times'),
    )
    op.create_index('ix_space_weather_events_activity_id', 'space_weather_events', ['activity_id'], unique=True)
    op.create_index('ix_space_weather_type_start', 'space_weather_events', ['event_type', 'start_time', 'id'])

    op.create_table('space_weather_event_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('space_weather_events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('linked_activity_id', sa.Text(), nullable=False),
        sa.Column('linked_event_type', sa.Text(), nullable=True),
        sa.UniqueConstraint('event_id', 'linked_activity_id', name='uq_space_weather_link'),
    )
    op.create_index('ix_space_weather_event_links_event_id', 'space_weather_event_links', ['event_id'])
    op.create_index('ix_space_weather_link_target', 'space_weather_event_links', ['linked_activity_id'])

    op.create_table('space_weather_sync_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('fetched_count', sa.Integer(), nullable=False),
        sa.Column('created_count', sa.Integer(), nullable=False),
        sa.Column('updated_count', sa.Integer(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('requested_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        _timestamp('started_at'),
        _timestamp('finished_at', True),
        sa.CheckConstraint(f'event_type IN ({TYPES})', name='ck_space_weather_sync_type'),
        sa.CheckConstraint("status IN ('success', 'failed')", name='ck_space_weather_sync_status'),
        sa.CheckConstraint('end_date >= start_date', name='ck_space_weather_sync_dates'),
    )

    op.create_table('proton_flux_readings',
        sa.Column('id', sa.Integer(), primary_key=True),
        _timestamp('observed_at'),
        sa.Column('energy_channel', sa.String(), nullable=False),
        sa.Column('flux_pfu', sa.Float(), nullable=False),
        sa.Column('satellite', sa.Text(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        _timestamp('recorded_at'),
        sa.UniqueConstraint('observed_at', 'energy_channel', 'satellite', 'source', name='uq_proton_flux_reading'),
        sa.CheckConstraint("energy_channel IN ('>=1 MeV', '>=5 MeV', '>=10 MeV', '>=30 MeV', '>=50 MeV', '>=60 MeV', '>=100 MeV', '>=500 MeV')", name='ck_proton_flux_channel'),
        sa.CheckConstraint('flux_pfu >= 0', name='ck_proton_flux_nonnegative'),
        sa.CheckConstraint("source IN ('noaa_swpc', 'simulation')", name='ck_proton_flux_source'),
    )
    op.create_index('ix_proton_flux_channel_time', 'proton_flux_readings', ['energy_channel', 'observed_at'])

    op.create_table('crew_activities',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=False),
        sa.Column('astronaut_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('activity_type', sa.String(), nullable=False),
        _timestamp('started_at'),
        _timestamp('ended_at', True),
        sa.Column('spacecraft_module_id', sa.Integer(), sa.ForeignKey('spacecraft_modules.id'), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('recorded_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        _timestamp('recorded_at'),
        sa.CheckConstraint("activity_type IN ('iva', 'eva', 'storm_shelter')", name='ck_crew_activity_type'),
        sa.CheckConstraint('ended_at IS NULL OR ended_at > started_at', name='ck_crew_activity_times'),
    )
    op.create_index('ix_crew_activities_mission_id', 'crew_activities', ['mission_id'])
    op.create_index('ix_crew_activity_astronaut_time', 'crew_activities', ['astronaut_id', 'started_at'])

    limits = op.create_table('radiation_exposure_limits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('profile_id', sa.Text(), nullable=False),
        sa.Column('organ', sa.String(), nullable=False),
        sa.Column('period', sa.String(), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(), nullable=False),
        sa.Column('source_reference', sa.Text(), nullable=False),
        sa.UniqueConstraint('profile_id', 'organ', 'period', name='uq_radiation_limit'),
        sa.CheckConstraint(f'organ IN ({ORGANS})', name='ck_radiation_limit_organ'),
        sa.CheckConstraint("period IN ('30_day', '1_year', 'career')", name='ck_radiation_limit_period'),
        sa.CheckConstraint("unit IN ('mGy-Eq', 'mGy')", name='ck_radiation_limit_unit'),
        sa.CheckConstraint('value > 0', name='ck_radiation_limit_value'),
    )
    op.bulk_insert(limits, [
        {'profile_id': LIMIT_PROFILE, 'organ': organ, 'period': period, 'value': value, 'unit': unit, 'source_reference': LIMIT_SOURCE}
        for organ, period, value, unit in TABLE_5_1
    ])

    op.create_table('radiation_dose_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=False),
        sa.Column('astronaut_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('space_weather_events.id'), nullable=True),
        sa.Column('organ', sa.String(), nullable=False),
        sa.Column('dose', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(), nullable=False),
        sa.Column('dose_rate_per_hour', sa.Float(), nullable=True),
        _timestamp('period_start'),
        _timestamp('period_end'),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('recorded_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        _timestamp('recorded_at'),
        sa.CheckConstraint(f'organ IN ({ORGANS})', name='ck_radiation_dose_organ'),
        sa.CheckConstraint("unit IN ('mGy-Eq', 'mGy')", name='ck_radiation_dose_unit'),
        sa.CheckConstraint("source IN ('dosimeter', 'model_estimate', 'simulation')", name='ck_radiation_dose_source'),
        sa.CheckConstraint('dose >= 0', name='ck_radiation_dose_nonnegative'),
        sa.CheckConstraint('dose_rate_per_hour IS NULL OR dose_rate_per_hour >= 0', name='ck_radiation_dose_rate'),
        sa.CheckConstraint('period_end >= period_start', name='ck_radiation_dose_period'),
    )
    op.create_index('ix_radiation_dose_records_mission_id', 'radiation_dose_records', ['mission_id'])
    op.create_index('ix_radiation_dose_astronaut_period', 'radiation_dose_records', ['astronaut_id', 'organ', 'period_start'])

    op.create_table('radiation_follow_ups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('space_weather_events.id'), nullable=False),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=False),
        sa.Column('astronaut_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('was_on_eva', sa.Boolean(), nullable=True),
        sa.Column('symptoms', sa.JSON(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        _timestamp('opened_at'),
        _timestamp('window_ends_at'),
        sa.Column('opened_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        _timestamp('closed_at', True),
        sa.Column('closed_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.UniqueConstraint('event_id', 'astronaut_id', name='uq_radiation_follow_up'),
        sa.CheckConstraint("status IN ('open', 'completed', 'cancelled')", name='ck_radiation_follow_up_status'),
        sa.CheckConstraint('window_ends_at > opened_at', name='ck_radiation_follow_up_window'),
    )
    op.create_index('ix_radiation_follow_ups_event_id', 'radiation_follow_ups', ['event_id'])
    op.create_index('ix_radiation_follow_ups_mission_id', 'radiation_follow_ups', ['mission_id'])


def downgrade():
    connection = op.get_bind()
    for table in ('radiation_follow_ups', 'radiation_dose_records', 'crew_activities'):
        if connection.execute(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table})')).scalar():
            raise RuntimeError(f'Preserve os registros de {table} antes de reverter esta migration')
    for table in TABLES:
        op.drop_table(table)
