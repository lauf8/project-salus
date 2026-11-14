"""Clima espacial e exposição à radiação.

Fundamentação: NASA SP-2009-3405, cap. 5 (Risk of Acute Radiation Syndromes Due to
Solar Particle Events). Flares e CMEs são tratados como precursores; SEPs, fluxo de
prótons e dosimetria descrevem a exposição. Um evento registrado no DONKI não
significa que um tripulante recebeu dose relevante.
"""

from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, DateTime, Index, Integer, JSON, ForeignKey, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


DONKI_EVENT_TYPES = ('FLR', 'CME', 'SEP')
RADIATION_ORGANS = ('lens', 'skin', 'bfo', 'heart', 'cns', 'cns_z_ge_10')


def _in(values) -> str:
    return ', '.join(f"'{value}'" for value in values)


class SpaceWeatherEvent(SQLModel, table=True):
    """Evento do catálogo NASA DONKI (flare, CME ou SEP)."""

    __tablename__ = 'space_weather_events'
    __table_args__ = (
        CheckConstraint(f'event_type IN ({_in(DONKI_EVENT_TYPES)})', name='ck_space_weather_event_type'),
        CheckConstraint('length(trim(activity_id)) > 0', name='ck_space_weather_activity_id'),
        CheckConstraint('end_time IS NULL OR end_time >= start_time', name='ck_space_weather_times'),
        Index('ix_space_weather_type_start', 'event_type', 'start_time', 'id'),
    )

    id: int | None = Field(default=None, primary_key=True)
    activity_id: str = Field(sa_column=Column(Text, nullable=False, unique=True, index=True))
    event_type: str
    catalog: str | None = Field(default=None, sa_type=Text)
    start_time: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    peak_time: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    end_time: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    source_location: str | None = Field(default=None, sa_type=Text)
    active_region_num: int | None = None

    # Flare: classe GOES (ex.: X1.9) e pico de fluxo de raios X equivalente em W/m².
    flare_class: str | None = Field(default=None, sa_type=Text)
    flare_peak_flux_wm2: float | None = None

    # CME: análise marcada como mais precisa pelo DONKI.
    cme_speed_kms: float | None = None
    cme_half_angle_deg: float | None = None
    cme_type: str | None = Field(default=None, sa_type=Text)
    cme_latitude: float | None = None
    cme_longitude: float | None = None
    cme_time_21_5: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))

    instruments: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    note: str | None = Field(default=None, sa_type=Text)
    link: str | None = Field(default=None, sa_type=Text)
    version_id: int | None = None
    submission_time: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    raw: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    first_seen_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    last_synced_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))

    @property
    def health_relevance(self) -> str:
        """FLR e CME são precursores; SEP é o evento de exposição (cap. 5)."""
        return 'exposure' if self.event_type == 'SEP' else 'precursor'


class SpaceWeatherEventLink(SQLModel, table=True):
    """Ligação informada pelo DONKI (linkedEvents).

    O evento ligado pode ser de um tipo não importado (IPS, GST...), por isso o
    identificador é guardado como texto e o tipo é extraído do próprio ID.
    """

    __tablename__ = 'space_weather_event_links'
    __table_args__ = (
        UniqueConstraint('event_id', 'linked_activity_id', name='uq_space_weather_link'),
        Index('ix_space_weather_link_target', 'linked_activity_id'),
    )

    id: int | None = Field(default=None, primary_key=True)
    event_id: int = Field(sa_column=Column(Integer, ForeignKey('space_weather_events.id', ondelete='CASCADE'), nullable=False, index=True))
    linked_activity_id: str = Field(sa_type=Text)
    linked_event_type: str | None = Field(default=None, sa_type=Text)


class SpaceWeatherSyncRun(SQLModel, table=True):
    """Registro de cada consulta ao DONKI, inclusive as que falharam."""

    __tablename__ = 'space_weather_sync_runs'
    __table_args__ = (
        CheckConstraint(f'event_type IN ({_in(DONKI_EVENT_TYPES)})', name='ck_space_weather_sync_type'),
        CheckConstraint("status IN ('success', 'failed')", name='ck_space_weather_sync_status'),
        CheckConstraint('end_date >= start_date', name='ck_space_weather_sync_dates'),
    )

    id: int | None = Field(default=None, primary_key=True)
    event_type: str
    start_date: date = Field(sa_column=Column(Date, nullable=False))
    end_date: date = Field(sa_column=Column(Date, nullable=False))
    status: str
    fetched_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    error: str | None = Field(default=None, sa_type=Text)
    requested_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    started_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class ProtonFluxReading(SQLModel, table=True):
    """Fluxo integral de prótons (GOES/NOAA SWPC) em pfu. O canal ≥30 MeV é o
    parâmetro usado no cap. 5 para comparar SEPs."""

    __tablename__ = 'proton_flux_readings'
    __table_args__ = (
        UniqueConstraint('observed_at', 'energy_channel', 'satellite', 'source', name='uq_proton_flux_reading'),
        CheckConstraint("energy_channel IN ('>=1 MeV', '>=5 MeV', '>=10 MeV', '>=30 MeV', '>=50 MeV', '>=60 MeV', '>=100 MeV', '>=500 MeV')", name='ck_proton_flux_channel'),
        CheckConstraint('flux_pfu >= 0', name='ck_proton_flux_nonnegative'),
        CheckConstraint("source IN ('noaa_swpc', 'simulation')", name='ck_proton_flux_source'),
        Index('ix_proton_flux_channel_time', 'energy_channel', 'observed_at'),
    )

    id: int | None = Field(default=None, primary_key=True)
    observed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    energy_channel: str
    flux_pfu: float
    satellite: str = Field(default='unknown', sa_type=Text)
    source: str = 'noaa_swpc'
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class CrewActivity(SQLModel, table=True):
    """Onde o tripulante estava: dentro da nave (IVA), em EVA ou no abrigo.
    A EVA é o cenário crítico para síndrome aguda da radiação (cap. 5)."""

    __tablename__ = 'crew_activities'
    __table_args__ = (
        CheckConstraint("activity_type IN ('iva', 'eva', 'storm_shelter')", name='ck_crew_activity_type'),
        CheckConstraint('ended_at IS NULL OR ended_at > started_at', name='ck_crew_activity_times'),
        Index('ix_crew_activity_astronaut_time', 'astronaut_id', 'started_at'),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key='missions.id', index=True)
    astronaut_id: int = Field(foreign_key='users.id')
    activity_type: str
    started_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    ended_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    spacecraft_module_id: int | None = Field(default=None, foreign_key='spacecraft_modules.id')
    note: str | None = Field(default=None, sa_type=Text)
    recorded_by_user_id: int = Field(foreign_key='users.id')
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class RadiationExposureLimit(SQLModel, table=True):
    """Limites de dose por órgão e período, versionados por perfil.

    O perfil inicial reproduz a Tabela 5-1 do NASA SP-2009-3405 (2009). Os limites
    da NASA foram revisados depois (NASA-STD-3001); crie um novo perfil em vez de
    alterar um perfil já usado.
    """

    __tablename__ = 'radiation_exposure_limits'
    __table_args__ = (
        UniqueConstraint('profile_id', 'organ', 'period', name='uq_radiation_limit'),
        CheckConstraint(f'organ IN ({_in(RADIATION_ORGANS)})', name='ck_radiation_limit_organ'),
        CheckConstraint("period IN ('30_day', '1_year', 'career')", name='ck_radiation_limit_period'),
        CheckConstraint("unit IN ('mGy-Eq', 'mGy')", name='ck_radiation_limit_unit'),
        CheckConstraint('value > 0', name='ck_radiation_limit_value'),
    )

    id: int | None = Field(default=None, primary_key=True)
    profile_id: str = Field(sa_type=Text)
    organ: str
    period: str
    value: float
    unit: str
    source_reference: str = Field(sa_type=Text)


class RadiationDoseRecord(SQLModel, table=True):
    """Dose estimada ou medida para um tripulante, opcionalmente ligada a um evento."""

    __tablename__ = 'radiation_dose_records'
    __table_args__ = (
        CheckConstraint(f'organ IN ({_in(RADIATION_ORGANS)})', name='ck_radiation_dose_organ'),
        CheckConstraint("unit IN ('mGy-Eq', 'mGy')", name='ck_radiation_dose_unit'),
        CheckConstraint("source IN ('dosimeter', 'model_estimate', 'simulation')", name='ck_radiation_dose_source'),
        CheckConstraint('dose >= 0', name='ck_radiation_dose_nonnegative'),
        CheckConstraint('dose_rate_per_hour IS NULL OR dose_rate_per_hour >= 0', name='ck_radiation_dose_rate'),
        CheckConstraint('period_end >= period_start', name='ck_radiation_dose_period'),
        Index('ix_radiation_dose_astronaut_period', 'astronaut_id', 'organ', 'period_start'),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key='missions.id', index=True)
    astronaut_id: int = Field(foreign_key='users.id')
    event_id: int | None = Field(default=None, foreign_key='space_weather_events.id')
    organ: str
    dose: float
    unit: str = 'mGy-Eq'
    dose_rate_per_hour: float | None = None
    period_start: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    period_end: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    source: str
    recorded_by_user_id: int = Field(foreign_key='users.id')
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class RadiationFollowUp(SQLModel, table=True):
    """Janela de observação de 48 h após um SEP relevante (efeitos prodrômicos:
    náusea, vômito, anorexia e fadiga; pele em caso de EVA)."""

    __tablename__ = 'radiation_follow_ups'
    __table_args__ = (
        UniqueConstraint('event_id', 'astronaut_id', name='uq_radiation_follow_up'),
        CheckConstraint("status IN ('open', 'completed', 'cancelled')", name='ck_radiation_follow_up_status'),
        CheckConstraint('window_ends_at > opened_at', name='ck_radiation_follow_up_window'),
    )

    id: int | None = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key='space_weather_events.id', index=True)
    mission_id: int = Field(foreign_key='missions.id', index=True)
    astronaut_id: int = Field(foreign_key='users.id')
    status: str = 'open'
    was_on_eva: bool | None = None
    symptoms: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    notes: str | None = Field(default=None, sa_type=Text)
    # opened_at é o início do SEP (início da janela); detected_at é quando o sistema
    # percebeu a exposição, que pode ser depois se o SEP chegou atrasado pelo DONKI.
    opened_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    window_ends_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    detected_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    # Nulo quando aberto pela sincronização agendada (sem usuário).
    opened_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    closed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    closed_by_user_id: int | None = Field(default=None, foreign_key='users.id')


class RadiationSymptomReport(SQLModel, table=True):
    """Relato de sintomas durante o acompanhamento pós-evento. Pode vir do próprio
    formulário do acompanhamento ou de uma medição de saúde com sintomas de radiação."""

    __tablename__ = 'radiation_symptom_reports'
    __table_args__ = (
        Index('ix_radiation_symptom_report_follow_up', 'follow_up_id', 'reported_at'),
    )

    id: int | None = Field(default=None, primary_key=True)
    follow_up_id: int = Field(sa_column=Column(Integer, ForeignKey('radiation_follow_ups.id', ondelete='CASCADE'), nullable=False))
    reported_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    symptoms: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    note: str | None = Field(default=None, sa_type=Text)
    observation_id: int | None = Field(default=None, foreign_key='health_observations.id')
    recorded_by_user_id: int = Field(foreign_key='users.id')
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class RadiationAlert(SQLModel, table=True):
    """Alerta de radiação. Tabela própria porque HealthAlert exige uma medição de
    origem; aqui a origem é um evento, um acompanhamento ou um registro de dose.

    dedupe_key identifica o alerta lógico (ex.: dose_limit:bfo:30_day); só pode
    haver um alerta ativo por astronauta e chave.
    """

    __tablename__ = 'radiation_alerts'
    __table_args__ = (
        CheckConstraint("severity IN ('attention', 'urgent', 'critical')", name='ck_radiation_alert_severity'),
        CheckConstraint("status IN ('open', 'acknowledged', 'resolved')", name='ck_radiation_alert_status'),
        CheckConstraint("rule_id IN ('sep_during_eva', 'proton_flux_during_eva', 'prodromal_vomiting', 'prodromal_symptoms', 'skin_reaction', 'late_symptoms', 'dose_limit')", name='ck_radiation_alert_rule'),
        Index('uq_radiation_alert_active', 'astronaut_id', 'dedupe_key', unique=True, postgresql_where=text("status IN ('open', 'acknowledged')"), sqlite_where=text("status IN ('open', 'acknowledged')")),
        Index('ix_radiation_alert_mission', 'mission_id', 'status', 'updated_at'),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key='missions.id')
    astronaut_id: int = Field(foreign_key='users.id', index=True)
    rule_id: str
    dedupe_key: str = Field(sa_type=Text)
    severity: str
    status: str = 'open'
    reason: str = Field(sa_type=Text)
    event_id: int | None = Field(default=None, foreign_key='space_weather_events.id')
    follow_up_id: int | None = Field(default=None, sa_column=Column(Integer, ForeignKey('radiation_follow_ups.id', ondelete='SET NULL')))
    dose_record_id: int | None = Field(default=None, sa_column=Column(Integer, ForeignKey('radiation_dose_records.id', ondelete='SET NULL')))
    details: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    acknowledged_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    acknowledged_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    resolved_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    resolved_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    resolution_note: str | None = Field(default=None, sa_type=Text)
