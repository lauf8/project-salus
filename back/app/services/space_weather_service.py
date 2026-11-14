"""Importação de eventos do NASA DONKI e consultas de clima espacial."""

import re
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, delete, select

from app.models.space_weather import RadiationExposureLimit, SpaceWeatherEvent, SpaceWeatherEventLink, SpaceWeatherSyncRun
from app.models.user import User
from app.providers.donki import DonkiClient, DonkiError
from app.schemas.space_weather import EventDetailResponse, EventResponse, ExposureLimitResponse, LinkedEventResponse, SyncRunResponse
from app.services.preflight_service import PreflightService


SYNC_WINDOW_DAYS = 30
ID_FIELDS = {'FLR': ('flrID', 'activityID'), 'CME': ('activityID',), 'SEP': ('sepID', 'activityID')}
START_FIELDS = {'FLR': 'beginTime', 'CME': 'startTime', 'SEP': 'eventTime'}
LINKED_TYPE = re.compile(r'-([A-Za-z]+)-\d+$')
FLARE_CLASS = re.compile(r'^\s*([ABCMX])\s*(\d+(?:\.\d+)?)?', re.IGNORECASE)
FLARE_BASE_FLUX = {'A': 1e-8, 'B': 1e-7, 'C': 1e-6, 'M': 1e-5, 'X': 1e-4}


# --- Normalização das respostas do DONKI -------------------------------------------------

def parse_donki_time(value) -> datetime | None:
    """Converte '2024-10-26T19:02Z' (formato do DONKI) em datetime UTC."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def linked_event_type(activity_id: str) -> str | None:
    """Extrai o tipo do identificador DONKI, ex.: '2024-10-26T15:34:00-IPS-001' -> 'IPS'."""
    match = LINKED_TYPE.search(activity_id or '')
    return match.group(1).upper() if match else None


def flare_peak_flux(class_type) -> float | None:
    """Classe GOES -> pico de fluxo de raios X (1–8 Å) em W/m². Ex.: 'X1.9' -> 1.9e-4."""
    match = FLARE_CLASS.match(class_type or '')
    if not match:
        return None
    multiplier = float(match.group(2)) if match.group(2) else 1.0
    return FLARE_BASE_FLUX[match.group(1).upper()] * multiplier


def _as_float(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _best_cme_analysis(analyses) -> dict | None:
    if not isinstance(analyses, list) or not analyses:
        return None
    candidates = [item for item in analyses if isinstance(item, dict)]
    if not candidates:
        return None
    accurate = [item for item in candidates if item.get('isMostAccurate')]
    return (accurate or candidates)[-1]


def normalize_event(event_type: str, item: dict) -> tuple[dict, list[str]] | None:
    """Transforma um item do DONKI em campos do modelo e lista de IDs ligados.

    Retorna None quando faltam identificador ou data inicial (o item é ignorado).
    """
    activity_id = next((item.get(key) for key in ID_FIELDS[event_type] if item.get(key)), None)
    start_time = parse_donki_time(item.get(START_FIELDS[event_type]))
    if not activity_id or start_time is None:
        return None

    instruments = [
        str(instrument.get('displayName')).strip()
        for instrument in item.get('instruments') or []
        if isinstance(instrument, dict) and instrument.get('displayName')
    ]
    fields = {
        'activity_id': str(activity_id).strip(),
        'event_type': event_type,
        'catalog': item.get('catalog'),
        'start_time': start_time,
        'peak_time': None,
        'end_time': None,
        'source_location': item.get('sourceLocation') or None,
        'active_region_num': _as_int(item.get('activeRegionNum')),
        'flare_class': None,
        'flare_peak_flux_wm2': None,
        'cme_speed_kms': None,
        'cme_half_angle_deg': None,
        'cme_type': None,
        'cme_latitude': None,
        'cme_longitude': None,
        'cme_time_21_5': None,
        'instruments': instruments,
        'note': item.get('note') or None,
        'link': item.get('link') or None,
        'version_id': _as_int(item.get('versionId')),
        'submission_time': parse_donki_time(item.get('submissionTime')),
        'raw': item,
    }

    if event_type == 'FLR':
        fields['peak_time'] = parse_donki_time(item.get('peakTime'))
        end_time = parse_donki_time(item.get('endTime'))
        fields['end_time'] = end_time if end_time and end_time >= start_time else None
        fields['flare_class'] = (item.get('classType') or '').strip() or None
        fields['flare_peak_flux_wm2'] = flare_peak_flux(fields['flare_class'])
    elif event_type == 'CME':
        analysis = _best_cme_analysis(item.get('cmeAnalyses'))
        if analysis:
            fields.update(
                cme_speed_kms=_as_float(analysis.get('speed')),
                cme_half_angle_deg=_as_float(analysis.get('halfAngle')),
                cme_type=analysis.get('type') or None,
                cme_latitude=_as_float(analysis.get('latitude')),
                cme_longitude=_as_float(analysis.get('longitude')),
                cme_time_21_5=parse_donki_time(analysis.get('time21_5')),
            )

    linked = []
    for link in item.get('linkedEvents') or []:
        target = link.get('activityID') if isinstance(link, dict) else None
        target = str(target).strip() if target else None
        if target and target != fields['activity_id'] and target not in linked:
            linked.append(target)
    return fields, linked


def date_windows(start: date, end: date, size_days: int = SYNC_WINDOW_DAYS):
    """Divide o intervalo em janelas para não sobrecarregar a API."""
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=size_days - 1), end)
        yield cursor, window_end
        cursor = window_end + timedelta(days=1)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


# --- Serviço -------------------------------------------------------------------------------

class SpaceWeatherService(PreflightService):
    def __init__(self, session: Session, user: User | None, donki: DonkiClient | None = None):
        super().__init__(session, user)
        self.donki = donki

    # Sincronização --------------------------------------------------------------------------

    def sync(self, start: date, end: date, event_types: list[str], check_permission: bool = True) -> list[SyncRunResponse]:
        """Busca FLR/CME/SEP no DONKI e grava/atualiza os eventos e suas ligações.

        Cada tipo é gravado numa transação própria. Falhas de rede ficam registradas
        em space_weather_sync_runs e não desfazem os tipos já importados.
        """
        if check_permission:
            self._catalog_writer()
        if self.donki is None:
            raise RuntimeError('DonkiClient não configurado')

        runs = []
        for event_type in event_types:
            run = SpaceWeatherSyncRun(
                event_type=event_type, start_date=start, end_date=end, status='success',
                requested_by_user_id=self.user.id if self.user else None,
            )
            try:
                items = []
                for window_start, window_end in date_windows(start, end):
                    items.extend(self.donki.fetch(event_type, window_start, window_end))
            except DonkiError as exc:
                run.status = 'failed'
                run.error = str(exc)
                run.finished_at = datetime.now(timezone.utc)
                self.session.add(run)
                self.session.commit()
                runs.append(SyncRunResponse.model_validate(run))
                continue

            try:
                run.fetched_count = len(items)
                created, updated = self._store(event_type, items)
                run.created_count, run.updated_count = created, updated
                run.finished_at = datetime.now(timezone.utc)
                self.session.add(run)
                self.session.commit()
            except Exception:
                self.session.rollback()
                raise
            runs.append(SyncRunResponse.model_validate(run))
        return runs

    def _store(self, event_type: str, items: list[dict]) -> tuple[int, int]:
        normalized: dict[str, tuple[dict, list[str]]] = {}
        for item in items:
            result = normalize_event(event_type, item)
            if result is not None:
                # Janelas consecutivas podem repetir um evento; vale a última versão.
                normalized[result[0]['activity_id']] = result

        created = updated = 0
        now = datetime.now(timezone.utc)
        for activity_id, (fields, linked) in normalized.items():
            row = self.session.exec(select(SpaceWeatherEvent).where(SpaceWeatherEvent.activity_id == activity_id)).first()
            if row is None:
                row = SpaceWeatherEvent(**fields, first_seen_at=now, last_synced_at=now)
                self.session.add(row)
                self.session.flush()
                created += 1
            else:
                if row.event_type != event_type:
                    raise HTTPException(409, f'O identificador {activity_id} já está registrado como {row.event_type}')
                if row.raw != fields['raw']:
                    updated += 1
                for key, value in fields.items():
                    setattr(row, key, value)
                row.last_synced_at = now
                self.session.add(row)
                self.session.flush()

            # O DONKI pode revisar as ligações; a lista atual substitui a anterior.
            self.session.exec(delete(SpaceWeatherEventLink).where(SpaceWeatherEventLink.event_id == row.id))
            for target in linked:
                self.session.add(SpaceWeatherEventLink(event_id=row.id, linked_activity_id=target, linked_event_type=linked_event_type(target)))
            self.session.flush()
        return created, updated

    # Consultas ------------------------------------------------------------------------------

    def list_events(self, event_type, start, end, page, per_page):
        statement = select(SpaceWeatherEvent)
        if event_type:
            statement = statement.where(SpaceWeatherEvent.event_type == event_type)
        statement = self._overlapping(statement, start, end)
        return self._page(statement.order_by(SpaceWeatherEvent.start_time.desc(), SpaceWeatherEvent.id.desc()), page, per_page)

    def get_event(self, activity_id: str) -> EventDetailResponse:
        row = self.session.exec(select(SpaceWeatherEvent).where(SpaceWeatherEvent.activity_id == activity_id)).first()
        if row is None:
            raise HTTPException(404, 'Evento de clima espacial não encontrado')
        return self._detail(row)

    def mission_events(self, mission_id: int, event_type, page, per_page):
        """Eventos que se sobrepõem ao período da missão (início efetivo ou lançamento
        previsto até o fim, ou até agora se a missão está aberta)."""
        mission, _ = self._access(mission_id)
        start = _utc(mission.started_at or mission.planned_launch_at)
        end = _utc(mission.ended_at) or datetime.now(timezone.utc)
        statement = select(SpaceWeatherEvent)
        if event_type:
            statement = statement.where(SpaceWeatherEvent.event_type == event_type)
        statement = self._overlapping(statement, start, end)
        return self._page(statement.order_by(SpaceWeatherEvent.start_time.desc(), SpaceWeatherEvent.id.desc()), page, per_page)

    def exposure_limits(self, profile_id: str | None):
        statement = select(RadiationExposureLimit)
        if profile_id:
            statement = statement.where(RadiationExposureLimit.profile_id == profile_id)
        rows = self.session.exec(statement.order_by(RadiationExposureLimit.profile_id, RadiationExposureLimit.organ, RadiationExposureLimit.period)).all()
        return [ExposureLimitResponse.model_validate(row) for row in rows]

    def last_sync_runs(self, limit: int = 20):
        rows = self.session.exec(select(SpaceWeatherSyncRun).order_by(SpaceWeatherSyncRun.started_at.desc(), SpaceWeatherSyncRun.id.desc()).limit(limit)).all()
        return [SyncRunResponse.model_validate(row) for row in rows]

    # Auxiliares -----------------------------------------------------------------------------

    @staticmethod
    def _overlapping(statement, start, end):
        if end is not None:
            statement = statement.where(SpaceWeatherEvent.start_time <= end)
        if start is not None:
            statement = statement.where(func.coalesce(SpaceWeatherEvent.end_time, SpaceWeatherEvent.start_time) >= start)
        return statement

    def _detail(self, row: SpaceWeatherEvent) -> EventDetailResponse:
        """Evento com as ligações nos dois sentidos (A -> B e B -> A), sem repetição."""
        outgoing = self.session.exec(select(SpaceWeatherEventLink).where(SpaceWeatherEventLink.event_id == row.id)).all()
        incoming = self.session.exec(
            select(SpaceWeatherEvent.activity_id).join(SpaceWeatherEventLink, SpaceWeatherEventLink.event_id == SpaceWeatherEvent.id)
            .where(SpaceWeatherEventLink.linked_activity_id == row.activity_id)
        ).all()
        targets = list(dict.fromkeys([link.linked_activity_id for link in outgoing] + list(incoming)))
        stored = {
            event.activity_id: event
            for event in self.session.exec(select(SpaceWeatherEvent).where(SpaceWeatherEvent.activity_id.in_(targets))).all()
        } if targets else {}

        linked = []
        for target in targets:
            event = stored.get(target)
            linked.append(LinkedEventResponse(
                activity_id=target,
                event_type=event.event_type if event else linked_event_type(target),
                stored=event is not None,
                event=EventResponse.model_validate(event) if event else None,
            ))
        # IDs do DONKI começam com o horário do evento, então a ordem textual é cronológica.
        linked.sort(key=lambda item: item.activity_id)
        return EventDetailResponse(**EventResponse.model_validate(row).model_dump(), linked_events=linked)
