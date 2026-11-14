"""Fluxo de exposição à radiação durante a missão.

Fundamentação: NASA SP-2009-3405, cap. 5. Resumo do fluxo:

1. O SEP chega pelo DONKI (ou é reprocessado manualmente). Quem estava em EVA no
   início do evento ganha uma janela de acompanhamento de 48 h e um alerta.
2. Durante a janela, sintomas prodrômicos (náusea, vômito, perda de apetite, fadiga)
   e reação de pele são registrados no acompanhamento ou numa medição de saúde.
3. O fluxo de prótons ≥10 MeV vem da NOAA SWPC (ou de uma simulação) e alimenta a
   estimativa simulada de dose. Doses medidas também podem ser registradas.
4. A dose acumulada é comparada com os limites por órgão e período.

Os limiares de alerta e a estimativa de dose são de SIMULAÇÃO, para demonstração.
Não substituem dosimetria real nem os critérios clínicos da equipe médica.
"""

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, update
from sqlmodel import Session, delete, select

from app.data.symptoms import RADIATION_SYMPTOMS
from app.models.preflight import Mission, MissionMember
from app.models.space_weather import (
    CrewActivity, ProtonFluxReading, RadiationAlert, RadiationDoseRecord, RadiationExposureLimit, RadiationFollowUp,
    RadiationSymptomReport, SpaceWeatherEvent, SpaceWeatherEventLink,
)
from app.models.user import User
from app.providers.swpc import SwpcClient, SwpcError
from app.schemas.radiation import (
    CrewActivityResponse, DoseResponse, DoseSimulationResponse, DoseSummary, DoseSummaryItem, EventChain,
    FollowUpResponse, ProtonFluxReadingResponse, ProtonFluxSimulationResponse, ProtonFluxSyncResponse,
    RadiationAlertResponse, SepProcessResponse, SymptomReportResponse, TimelineResponse,
)
from app.schemas.space_weather import EventResponse
from app.services.preflight_service import PreflightService, transactional


DEFAULT_LIMIT_PROFILE = 'nasa-sp-2009-3405-table-5-1'
FOLLOW_UP_WINDOW = timedelta(hours=48)
# Uma EVA sem fim registrado só conta se começou até 12 h antes do SEP (EVAs reais
# duram menos que isso); evita que um registro esquecido abra acompanhamentos.
OPEN_EVA_LOOKBACK = timedelta(hours=12)

SEVERITY_RANK = {'attention': 1, 'urgent': 2, 'critical': 3}
# Escala S da NOAA para o fluxo ≥10 MeV (pfu): S1 = 10, S2 = 100, S3 = 1000.
FLUX_CHANNEL = '>=10 MeV'
FLUX_S1, FLUX_S2, FLUX_S3 = 10.0, 100.0, 1000.0
# Fração do limite de dose que gera alerta (perfil de simulação).
DOSE_THRESHOLDS = ((1.0, 'critical'), (0.75, 'urgent'), (0.5, 'attention'))
PERIOD_DAYS = {'30_day': 30, '1_year': 365, 'career': None}

# Estimativa didática de dose a partir do fluxo ≥10 MeV. Não é um modelo físico de
# transporte: só mostra a ordem de grandeza e o efeito da blindagem.
SKIN_DOSE_RATE_PER_PFU = 0.02  # mGy-Eq/h por pfu, em EVA (traje sem blindagem da nave)
SHIELDING_FACTOR = {'eva': 1.0, 'iva': 0.15, 'storm_shelter': 0.05}
ORGAN_FACTOR = {'skin': 1.0, 'lens': 0.9, 'cns': 0.35, 'bfo': 0.3, 'heart': 0.3}
ACTIVITY_PRIORITY = {'eva': 0, 'storm_shelter': 1, 'iva': 2}
SIMULATED_BASELINE_PFU = 0.5

ORGAN_LABELS = {'lens': 'cristalino', 'skin': 'pele', 'bfo': 'órgãos formadores de sangue', 'heart': 'coração', 'cns': 'sistema nervoso central', 'cns_z_ge_10': 'SNC (íons Z ≥ 10)'}
PERIOD_LABELS = {'30_day': '30 dias', '1_year': '1 ano', 'career': 'carreira'}
FLUX_CHANNELS = ('>=1 MeV', '>=5 MeV', '>=10 MeV', '>=30 MeV', '>=50 MeV', '>=60 MeV', '>=100 MeV', '>=500 MeV')


def utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def now() -> datetime:
    return datetime.now(timezone.utc)


def flux_severity(peak: float | None) -> str | None:
    if peak is None or peak < FLUX_S1:
        return None
    return 'critical' if peak >= FLUX_S3 else 'urgent' if peak >= FLUX_S2 else 'attention'


def dose_severity(fraction: float) -> str | None:
    return next((severity for threshold, severity in DOSE_THRESHOLDS if fraction >= threshold), None)


def simulated_flux(hours: float, peak: float, rise: float, decay: float) -> float:
    """Subida linear até o pico e queda exponencial, sobre um fundo de 0,5 pfu."""
    amplitude = peak - SIMULATED_BASELINE_PFU
    if hours <= rise:
        return SIMULATED_BASELINE_PFU + amplitude * hours / rise
    return SIMULATED_BASELINE_PFU + amplitude * math.exp(-(hours - rise) / decay)


def parse_swpc_reading(item: dict) -> tuple[datetime, str, str, float] | None:
    """Converte uma leitura do SWPC (time_tag, satellite, flux, energy). None se inválida."""
    energy = str(item.get('energy') or '').replace(' ', '').replace('MeV', ' MeV')
    if energy not in FLUX_CHANNELS:
        return None
    try:
        flux = float(item.get('flux'))
        observed = datetime.fromisoformat(str(item.get('time_tag')).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(flux) or flux < 0:
        return None
    satellite = item.get('satellite')
    return utc(observed), energy, f'GOES-{satellite}' if satellite not in (None, '') else 'unknown', flux


class RadiationService(PreflightService):
    def __init__(self, session: Session, user: User | None):
        super().__init__(session, user)

    @property
    def actor_id(self) -> int | None:
        return self.user.id if self.user else None

    # --- Permissões ------------------------------------------------------------------------

    def _member(self, mission_id):
        """Qualquer membro da missão; devolve (missão, vínculo, é_médico_de_voo)."""
        mission, member = self._access(mission_id)
        surgeon = member.role == 'flight_surgeon' and bool(self.user.is_physician)
        return mission, member, surgeon

    def _surgeon(self, mission_id):
        mission, member, surgeon = self._member(mission_id)
        if not surgeon:
            raise HTTPException(403, 'Somente o médico de voo da missão pode realizar esta operação')
        return mission, member

    def _crew(self, mission_id, astronaut_id):
        member = self.session.exec(select(MissionMember).where(
            MissionMember.mission_id == mission_id, MissionMember.user_id == astronaut_id, MissionMember.role == 'astronaut',
        )).first()
        if member is None:
            raise HTTPException(404, 'Astronauta não encontrado na tripulação desta missão')
        return member

    def _clinical_view(self, mission_id, astronaut_id=None):
        """Dados clínicos: o médico de voo vê todos; o astronauta vê apenas os próprios."""
        mission, member, surgeon = self._member(mission_id)
        if surgeon:
            return mission, None
        if member.role == 'astronaut' and astronaut_id in (None, self.user.id):
            return mission, self.user.id
        raise HTTPException(403, 'Acesso não autorizado aos dados de radiação deste astronauta')

    def _self_or_surgeon(self, mission_id, astronaut_id):
        mission, member, surgeon = self._member(mission_id)
        if not surgeon and self.user.id != astronaut_id:
            raise HTTPException(403, 'Somente o próprio astronauta ou o médico de voo podem registrar')
        return mission, surgeon

    # --- Alertas ----------------------------------------------------------------------------

    def _raise_alert(self, mission_id, astronaut_id, rule_id, key, severity, reason, details=None, **links) -> bool:
        """Cria o alerta ou eleva a severidade do alerta ativo com a mesma chave.
        Devolve True quando um alerta novo foi criado."""
        alert = self.session.exec(select(RadiationAlert).where(
            RadiationAlert.astronaut_id == astronaut_id, RadiationAlert.dedupe_key == key,
            RadiationAlert.status.in_(['open', 'acknowledged']),
        )).first()
        timestamp = now()
        if alert is None:
            self.session.add(RadiationAlert(
                mission_id=mission_id, astronaut_id=astronaut_id, rule_id=rule_id, dedupe_key=key, severity=severity,
                reason=reason, details=details or {}, created_at=timestamp, updated_at=timestamp, **links,
            ))
            self.session.flush()
            return True
        if SEVERITY_RANK[severity] > SEVERITY_RANK[alert.severity]:
            alert.severity = severity
            alert.status = 'open'
            alert.acknowledged_at = None
            alert.acknowledged_by_user_id = None
        if SEVERITY_RANK[severity] >= SEVERITY_RANK[alert.severity]:
            alert.reason = reason
            alert.details = details or {}
            for name, value in links.items():
                if value is not None:
                    setattr(alert, name, value)
        alert.updated_at = timestamp
        self.session.add(alert)
        self.session.flush()
        return False

    def _alert_response(self, alert, can_resolve):
        return RadiationAlertResponse.model_validate({**alert.model_dump(), 'can_resolve': can_resolve and alert.status != 'resolved'})

    def list_alerts(self, mission_id, status, astronaut_id, page, per_page):
        _, only = self._clinical_view(mission_id, astronaut_id)
        statement = select(RadiationAlert).where(RadiationAlert.mission_id == mission_id)
        target = only or astronaut_id
        if target is not None:
            statement = statement.where(RadiationAlert.astronaut_id == target)
        if status == 'active':
            statement = statement.where(RadiationAlert.status.in_(['open', 'acknowledged']))
        elif status != 'all':
            statement = statement.where(RadiationAlert.status == status)
        resolved_last = case((RadiationAlert.status == 'resolved', 1), else_=0)
        severity = case((RadiationAlert.severity == 'critical', 3), (RadiationAlert.severity == 'urgent', 2), else_=1)
        result = self._page(statement.order_by(resolved_last, severity.desc(), RadiationAlert.updated_at.desc(), RadiationAlert.id.desc()), page, per_page)
        result['data'] = [self._alert_response(alert, only is None) for alert in result['data']]
        return result

    def _mission_alert(self, mission_id, alert_id):
        alert = self.session.get(RadiationAlert, alert_id)
        if alert is None or alert.mission_id != mission_id:
            raise HTTPException(404, 'Alerta de radiação não encontrado nesta missão')
        return alert

    @transactional
    def acknowledge_alert(self, mission_id, alert_id):
        alert = self._mission_alert(mission_id, alert_id)
        _, surgeon = self._self_or_surgeon(mission_id, alert.astronaut_id)
        if alert.status == 'resolved':
            raise HTTPException(409, 'Um alerta resolvido não pode ser reconhecido')
        if alert.status == 'open':
            alert.status = 'acknowledged'
            alert.acknowledged_at = alert.updated_at = now()
            alert.acknowledged_by_user_id = self.user.id
            self.session.add(alert)
            self.session.flush()
        return self._alert_response(alert, surgeon)

    @transactional
    def resolve_alert(self, mission_id, alert_id, payload):
        self._surgeon(mission_id)
        alert = self._mission_alert(mission_id, alert_id)
        if alert.status != 'resolved':
            alert.status = 'resolved'
            alert.resolved_at = alert.updated_at = now()
            alert.resolved_by_user_id = self.user.id
            alert.resolution_note = payload.note
            self.session.add(alert)
            self.session.flush()
        return self._alert_response(alert, True)

    # --- Atividade da tripulação -------------------------------------------------------------

    def list_activities(self, mission_id, astronaut_id, page, per_page):
        self._member(mission_id)
        statement = select(CrewActivity).where(CrewActivity.mission_id == mission_id)
        if astronaut_id is not None:
            statement = statement.where(CrewActivity.astronaut_id == astronaut_id)
        return self._page(statement.order_by(CrewActivity.started_at.desc(), CrewActivity.id.desc()), page, per_page)

    def _activity_writer(self, mission_id, astronaut_id):
        mission, member, surgeon = self._member(mission_id)
        if not (surgeon or member.role == 'mission_admin' or self.user.id == astronaut_id):
            raise HTTPException(403, 'Somente o próprio astronauta, o médico de voo ou o administrador da missão podem registrar a atividade')
        return mission

    def _validate_activity_window(self, mission, started_at, ended_at):
        mission_start = utc(mission.started_at or mission.planned_launch_at)
        mission_end = utc(mission.ended_at)
        if started_at < mission_start or (mission_end and started_at > mission_end):
            raise HTTPException(422, 'A atividade deve começar dentro do período da missão')
        if ended_at and mission_end and ended_at > mission_end:
            raise HTTPException(422, 'A atividade deve terminar dentro do período da missão')

    def _check_overlap(self, activity):
        """Um astronauta não pode estar em duas atividades ao mesmo tempo."""
        start, end = utc(activity.started_at), utc(activity.ended_at)
        statement = select(CrewActivity).where(
            CrewActivity.astronaut_id == activity.astronaut_id,
            or_(CrewActivity.ended_at.is_(None), CrewActivity.ended_at > start),
        )
        if activity.id is not None:
            statement = statement.where(CrewActivity.id != activity.id)
        if end is not None:
            statement = statement.where(CrewActivity.started_at < end)
        conflict = self.session.exec(statement).first()
        if conflict is not None:
            raise HTTPException(409, f'Já existe uma atividade registrada nesse horário (#{conflict.id}); encerre-a antes')

    @transactional
    def create_activity(self, mission_id, payload):
        mission = self._activity_writer(mission_id, payload.astronaut_id)
        self._crew(mission_id, payload.astronaut_id)
        self._validate_activity_window(mission, payload.started_at, payload.ended_at)
        activity = CrewActivity(**payload.model_dump(), mission_id=mission_id, recorded_by_user_id=self.user.id)
        self._check_overlap(activity)
        self.session.add(activity)
        self.session.flush()
        self._after_activity(activity)
        return CrewActivityResponse.model_validate(activity)

    @transactional
    def end_activity(self, mission_id, activity_id, payload):
        activity = self.session.get(CrewActivity, activity_id)
        if activity is None or activity.mission_id != mission_id:
            raise HTTPException(404, 'Atividade não encontrada nesta missão')
        mission = self._activity_writer(mission_id, activity.astronaut_id)
        if activity.ended_at is not None:
            raise HTTPException(409, 'A atividade já foi encerrada')
        if payload.ended_at <= utc(activity.started_at):
            raise HTTPException(422, 'ended_at deve ser posterior ao início da atividade')
        self._validate_activity_window(mission, utc(activity.started_at), payload.ended_at)
        activity.ended_at = payload.ended_at
        if payload.note:
            activity.note = f'{activity.note}\n{payload.note}' if activity.note else payload.note
        self._check_overlap(activity)
        self.session.add(activity)
        self.session.flush()
        self._after_activity(activity)
        return CrewActivityResponse.model_validate(activity)

    def _after_activity(self, activity):
        """Uma EVA registrada depois do SEP (ou do fluxo alto) também gera acompanhamento."""
        if activity.activity_type != 'eva':
            return
        start, end = utc(activity.started_at), utc(activity.ended_at) or now()
        seps = self.session.exec(select(SpaceWeatherEvent).where(
            SpaceWeatherEvent.event_type == 'SEP', SpaceWeatherEvent.start_time <= end,
            func.coalesce(SpaceWeatherEvent.end_time, SpaceWeatherEvent.start_time) >= start,
        )).all()
        for sep in seps:
            self.process_sep(sep)
        self._flux_eva_alerts(start, end)

    # --- SEP: janela de 48 h ------------------------------------------------------------------

    def _eva_during(self, start, end):
        return self.session.exec(select(CrewActivity).where(
            CrewActivity.activity_type == 'eva', CrewActivity.started_at <= end,
            or_(CrewActivity.ended_at >= start, and_(CrewActivity.ended_at.is_(None), CrewActivity.started_at >= start - OPEN_EVA_LOOKBACK)),
        ).order_by(CrewActivity.started_at, CrewActivity.id)).all()

    def _peak_flux(self, start, end):
        return self.session.exec(select(func.max(ProtonFluxReading.flux_pfu)).where(
            ProtonFluxReading.energy_channel == FLUX_CHANNEL,
            ProtonFluxReading.observed_at >= start, ProtonFluxReading.observed_at <= end,
        )).one()

    def process_sep(self, event) -> tuple[int, int]:
        """Abre a janela de 48 h para quem estava em EVA no SEP. Idempotente.

        Devolve (acompanhamentos abertos, alertas criados)."""
        if event.event_type != 'SEP':
            return 0, 0
        start = utc(event.start_time)
        end = utc(event.end_time) or start
        opened = created = 0
        peak = self._peak_flux(start, start + FOLLOW_UP_WINDOW)
        seen = set()
        for activity in self._eva_during(start, end):
            if (activity.astronaut_id, activity.mission_id) in seen:
                continue
            seen.add((activity.astronaut_id, activity.mission_id))
            crew = self.session.exec(select(MissionMember).where(
                MissionMember.mission_id == activity.mission_id, MissionMember.user_id == activity.astronaut_id,
                MissionMember.role == 'astronaut',
            )).first()
            if crew is None:
                continue
            follow_up = self.session.exec(select(RadiationFollowUp).where(
                RadiationFollowUp.event_id == event.id, RadiationFollowUp.astronaut_id == activity.astronaut_id,
            )).first()
            if follow_up is None:
                follow_up = RadiationFollowUp(
                    event_id=event.id, mission_id=activity.mission_id, astronaut_id=activity.astronaut_id,
                    status='open', was_on_eva=True, symptoms=[], opened_at=start,
                    window_ends_at=start + FOLLOW_UP_WINDOW, detected_at=now(), opened_by_user_id=self.actor_id,
                )
                self.session.add(follow_up)
                self.session.flush()
                opened += 1
            severity = 'critical' if peak is not None and peak >= FLUX_S3 else 'urgent'
            flux_text = f' Pico de prótons ≥10 MeV nas 48 h: {peak:g} pfu.' if peak is not None else ' Sem leituras de fluxo de prótons para o período.'
            created += self._raise_alert(
                activity.mission_id, activity.astronaut_id, 'sep_during_eva', f'sep_during_eva:{event.id}', severity,
                f'Tripulante em EVA durante o SEP {event.activity_id}. Janela de observação de 48 h aberta '
                f'(até {follow_up.window_ends_at:%Y-%m-%d %H:%M} UTC): registre náusea, vômito, perda de apetite, fadiga e pele.{flux_text}',
                {'activity_id': activity.id, 'peak_flux_pfu': peak},
                event_id=event.id, follow_up_id=follow_up.id,
            )
        return opened, created

    def process_seps(self, events) -> tuple[int, int]:
        totals = [0, 0]
        for event in events:
            opened, created = self.process_sep(event)
            totals[0] += opened
            totals[1] += created
        return totals[0], totals[1]

    @transactional
    def reprocess_event(self, activity_id):
        self._catalog_writer()
        event = self.session.exec(select(SpaceWeatherEvent).where(SpaceWeatherEvent.activity_id == activity_id)).first()
        if event is None:
            raise HTTPException(404, 'Evento de clima espacial não encontrado')
        if event.event_type != 'SEP':
            raise HTTPException(422, 'Somente SEPs abrem acompanhamento; flares e CMEs são precursores')
        opened, created = self.process_sep(event)
        return SepProcessResponse(event_activity_id=activity_id, follow_ups_opened=opened, alerts_created=created)

    # --- Acompanhamento pós-evento -------------------------------------------------------------

    def _follow_up_response(self, follow_up):
        event = self.session.get(SpaceWeatherEvent, follow_up.event_id)
        reports = self.session.exec(select(RadiationSymptomReport).where(
            RadiationSymptomReport.follow_up_id == follow_up.id,
        ).order_by(RadiationSymptomReport.reported_at, RadiationSymptomReport.id)).all()
        return FollowUpResponse.model_validate({
            **follow_up.model_dump(), 'event_activity_id': event.activity_id,
            'window_active': follow_up.status == 'open' and now() <= utc(follow_up.window_ends_at),
            'reports': [SymptomReportResponse.model_validate(report) for report in reports],
        })

    def list_follow_ups(self, mission_id, status, astronaut_id):
        _, only = self._clinical_view(mission_id, astronaut_id)
        statement = select(RadiationFollowUp).where(RadiationFollowUp.mission_id == mission_id)
        target = only or astronaut_id
        if target is not None:
            statement = statement.where(RadiationFollowUp.astronaut_id == target)
        if status != 'all':
            statement = statement.where(RadiationFollowUp.status == status)
        rows = self.session.exec(statement.order_by(RadiationFollowUp.opened_at.desc(), RadiationFollowUp.id.desc())).all()
        return [self._follow_up_response(row) for row in rows]

    def _mission_follow_up(self, mission_id, follow_up_id):
        follow_up = self.session.get(RadiationFollowUp, follow_up_id)
        if follow_up is None or follow_up.mission_id != mission_id:
            raise HTTPException(404, 'Acompanhamento não encontrado nesta missão')
        return follow_up

    def get_follow_up(self, mission_id, follow_up_id):
        follow_up = self._mission_follow_up(mission_id, follow_up_id)
        self._clinical_view(mission_id, follow_up.astronaut_id)
        return self._follow_up_response(follow_up)

    @transactional
    def add_report(self, mission_id, follow_up_id, payload):
        follow_up = self._mission_follow_up(mission_id, follow_up_id)
        self._self_or_surgeon(mission_id, follow_up.astronaut_id)
        reported_at = payload.reported_at or now()
        self._record_report(follow_up, payload.symptoms, reported_at, payload.note)
        return self._follow_up_response(follow_up)

    def _record_report(self, follow_up, symptoms, reported_at, note=None, observation_id=None):
        if follow_up.status != 'open':
            raise HTTPException(409, 'O acompanhamento já foi encerrado')
        if reported_at < utc(follow_up.opened_at):
            raise HTTPException(422, 'O relato não pode ser anterior ao início do SEP')
        self.session.add(RadiationSymptomReport(
            follow_up_id=follow_up.id, reported_at=reported_at, symptoms=list(symptoms), note=note,
            observation_id=observation_id, recorded_by_user_id=self.user.id,
        ))
        follow_up.symptoms = sorted(set(follow_up.symptoms) | set(symptoms))
        self.session.add(follow_up)
        self.session.flush()
        self._evaluate_symptoms(follow_up, set(symptoms), reported_at)

    def _evaluate_symptoms(self, follow_up, symptoms, reported_at):
        if not symptoms:
            return
        labels = ', '.join(RADIATION_SYMPTOMS[key] for key in sorted(symptoms))
        base = dict(event_id=follow_up.event_id, follow_up_id=follow_up.id)
        details = {'symptoms': sorted(symptoms), 'reported_at': reported_at.isoformat()}
        mission, astronaut = follow_up.mission_id, follow_up.astronaut_id
        if reported_at > utc(follow_up.window_ends_at):
            self._raise_alert(mission, astronaut, 'late_symptoms', f'late_symptoms:{follow_up.id}', 'attention',
                              f'Sintomas relatados após a janela de 48 h: {labels}. Avalie outras causas além da radiação.', details, **base)
            return
        if 'vomiting' in symptoms:
            self._raise_alert(mission, astronaut, 'prodromal_vomiting', f'prodromal_vomiting:{follow_up.id}', 'critical',
                              'Vômito na janela de 48 h após o SEP. Na síndrome aguda da radiação, vômito precoce sugere dose '
                              'relevante: avalie o tripulante, confira a dose estimada e siga o protocolo médico.', details, **base)
        prodromal = symptoms & {'nausea', 'anorexia', 'fatigue'}
        if prodromal:
            self._raise_alert(mission, astronaut, 'prodromal_symptoms', f'prodromal_symptoms:{follow_up.id}', 'urgent',
                              f'Sintomas prodrômicos na janela de 48 h após o SEP: {", ".join(RADIATION_SYMPTOMS[key] for key in sorted(prodromal))}. '
                              'Reavalie o tripulante e acompanhe a evolução.', details, **base)
        if 'skin_erythema' in symptoms:
            context = ' O tripulante estava em EVA, cenário de maior dose na pele.' if follow_up.was_on_eva else ''
            self._raise_alert(mission, astronaut, 'skin_reaction', f'skin_reaction:{follow_up.id}', 'urgent',
                              f'Reação de pele relatada após o SEP.{context} Examine e registre a área afetada.', details, **base)

    def report_from_observation(self, observation) -> int:
        """Sintomas de radiação numa medição de saúde entram nos acompanhamentos abertos
        cuja janela inclui o horário da coleta. Devolve quantos acompanhamentos receberam."""
        symptoms = sorted(set(observation.symptoms or []) & set(RADIATION_SYMPTOMS))
        if not symptoms:
            return 0
        collected = utc(observation.collected_at)
        statement = select(RadiationFollowUp).where(
            RadiationFollowUp.astronaut_id == observation.astronaut_id, RadiationFollowUp.status == 'open',
            RadiationFollowUp.opened_at <= collected, RadiationFollowUp.window_ends_at >= collected,
        )
        if observation.mission_id is not None:
            statement = statement.where(RadiationFollowUp.mission_id == observation.mission_id)
        follow_ups = self.session.exec(statement).all()
        for follow_up in follow_ups:
            self._record_report(follow_up, symptoms, collected, 'Registrado a partir de uma medição de saúde.', observation.id)
        return len(follow_ups)

    @transactional
    def close_follow_up(self, mission_id, follow_up_id, payload):
        self._surgeon(mission_id)
        follow_up = self._mission_follow_up(mission_id, follow_up_id)
        if follow_up.status != 'open':
            raise HTTPException(409, 'O acompanhamento já foi encerrado')
        follow_up.status = payload.status
        follow_up.notes = payload.notes
        follow_up.closed_at = now()
        follow_up.closed_by_user_id = self.user.id
        self.session.add(follow_up)
        self.session.flush()
        return self._follow_up_response(follow_up)

    # --- Doses ----------------------------------------------------------------------------------

    def _event_by_activity_id(self, activity_id):
        if activity_id is None:
            return None
        event = self.session.exec(select(SpaceWeatherEvent).where(SpaceWeatherEvent.activity_id == activity_id)).first()
        if event is None:
            raise HTTPException(404, 'Evento de clima espacial não encontrado')
        return event

    @transactional
    def create_dose(self, mission_id, payload):
        self._surgeon(mission_id)
        self._crew(mission_id, payload.astronaut_id)
        event = self._event_by_activity_id(payload.event_activity_id)
        record = RadiationDoseRecord(
            **payload.model_dump(exclude={'event_activity_id'}), mission_id=mission_id,
            event_id=event.id if event else None, recorded_by_user_id=self.user.id,
        )
        self.session.add(record)
        self.session.flush()
        self._evaluate_doses(mission_id, payload.astronaut_id, payload.period_end, record.id)
        return DoseResponse.model_validate(record)

    def list_doses(self, mission_id, astronaut_id, page, per_page):
        _, only = self._clinical_view(mission_id, astronaut_id)
        statement = select(RadiationDoseRecord).where(RadiationDoseRecord.mission_id == mission_id)
        target = only or astronaut_id
        if target is not None:
            statement = statement.where(RadiationDoseRecord.astronaut_id == target)
        return self._page(statement.order_by(RadiationDoseRecord.period_end.desc(), RadiationDoseRecord.id.desc()), page, per_page)

    def dose_summary(self, mission_id, astronaut_id, profile_id, as_of):
        mission, _ = self._clinical_view(mission_id, astronaut_id)
        self._crew(mission_id, astronaut_id)
        if as_of is None:
            as_of = min(utc(mission.ended_at) or now(), now())
        return DoseSummary(astronaut_id=astronaut_id, profile_id=profile_id, as_of=as_of, items=self._dose_totals(astronaut_id, as_of, profile_id))

    def _dose_totals(self, astronaut_id, as_of, profile_id=DEFAULT_LIMIT_PROFILE):
        """Soma a dose de toda a carreira do astronauta (todas as missões) por órgão e
        período. Cada registro conta inteiro na data de period_end."""
        limits = self.session.exec(select(RadiationExposureLimit).where(RadiationExposureLimit.profile_id == profile_id)).all()
        if not limits:
            raise HTTPException(404, 'Perfil de limites de dose não encontrado')
        items = []
        for limit in sorted(limits, key=lambda row: (row.organ, list(PERIOD_DAYS).index(row.period))):
            statement = select(func.coalesce(func.sum(RadiationDoseRecord.dose), 0.0)).where(
                RadiationDoseRecord.astronaut_id == astronaut_id, RadiationDoseRecord.organ == limit.organ,
                RadiationDoseRecord.unit == limit.unit, RadiationDoseRecord.period_end <= as_of,
            )
            days = PERIOD_DAYS[limit.period]
            if days is not None:
                statement = statement.where(RadiationDoseRecord.period_end > as_of - timedelta(days=days))
            total = float(self.session.exec(statement).one())
            fraction = total / limit.value
            items.append(DoseSummaryItem(
                organ=limit.organ, period=limit.period, total=round(total, 4), unit=limit.unit, limit=limit.value,
                fraction=round(fraction, 4), severity=dose_severity(fraction),
            ))
        return items

    def _evaluate_doses(self, mission_id, astronaut_id, as_of, dose_record_id=None) -> int:
        created = 0
        for item in self._dose_totals(astronaut_id, utc(as_of)):
            if item.severity is None:
                continue
            created += self._raise_alert(
                mission_id, astronaut_id, 'dose_limit', f'dose_limit:{item.organ}:{item.period}', item.severity,
                f'Dose acumulada em {ORGAN_LABELS[item.organ]} ({PERIOD_LABELS[item.period]}): {item.total:g} de {item.limit:g} '
                f'{item.unit} ({item.fraction:.0%} do limite do perfil {DEFAULT_LIMIT_PROFILE}).',
                {'organ': item.organ, 'period': item.period, 'total': item.total, 'limit': item.limit, 'fraction': item.fraction},
                dose_record_id=dose_record_id,
            )
        return created

    @transactional
    def simulate_doses(self, mission_id, payload):
        """Estima a dose de cada tripulante integrando o fluxo ≥10 MeV no período,
        com o fator de blindagem da atividade em cada intervalo (IVA quando não há
        registro). Substitui uma simulação anterior do mesmo período."""
        self._surgeon(mission_id)
        event = self._event_by_activity_id(payload.event_activity_id)
        crew_ids = self.session.exec(select(MissionMember.user_id).where(
            MissionMember.mission_id == mission_id, MissionMember.role == 'astronaut',
        )).all()
        astronauts = payload.astronaut_ids or list(crew_ids)
        for astronaut_id in astronauts:
            self._crew(mission_id, astronaut_id)
        points = self._flux_series(payload.start, payload.end)
        if len(points) < 2:
            raise HTTPException(422, 'Não há leituras suficientes de prótons ≥10 MeV no período. Importe da NOAA SWPC ou simule o fluxo.')

        records = []
        hours = (payload.end - payload.start).total_seconds() / 3600
        for astronaut_id in astronauts:
            activities = self.session.exec(select(CrewActivity).where(
                CrewActivity.mission_id == mission_id, CrewActivity.astronaut_id == astronaut_id,
                CrewActivity.started_at <= payload.end,
                or_(CrewActivity.ended_at.is_(None), CrewActivity.ended_at >= payload.start),
            )).all()
            skin = 0.0
            for (time, flux), (next_time, _) in zip(points, points[1:]):
                interval = (next_time - time).total_seconds() / 3600
                activity = self._activity_at(activities, time + (next_time - time) / 2)
                skin += SKIN_DOSE_RATE_PER_PFU * flux * SHIELDING_FACTOR[activity] * interval
            previous = select(RadiationDoseRecord.id).where(
                RadiationDoseRecord.mission_id == mission_id, RadiationDoseRecord.astronaut_id == astronaut_id,
                RadiationDoseRecord.source == 'simulation', RadiationDoseRecord.period_start == payload.start,
                RadiationDoseRecord.period_end == payload.end,
            )
            # Os alertas continuam; só perdem o vínculo com o registro substituído.
            self.session.exec(update(RadiationAlert).where(RadiationAlert.dose_record_id.in_(previous)).values(dose_record_id=None))
            self.session.exec(delete(RadiationDoseRecord).where(RadiationDoseRecord.id.in_(previous)))
            for organ, factor in ORGAN_FACTOR.items():
                dose = round(skin * factor, 4)
                record = RadiationDoseRecord(
                    mission_id=mission_id, astronaut_id=astronaut_id, event_id=event.id if event else None, organ=organ,
                    dose=dose, unit='mGy-Eq', dose_rate_per_hour=round(dose / hours, 4), period_start=payload.start,
                    period_end=payload.end, source='simulation', recorded_by_user_id=self.user.id,
                )
                self.session.add(record)
                records.append(record)
            self.session.flush()
            self._evaluate_doses(mission_id, astronaut_id, payload.end, records[-len(ORGAN_FACTOR)].id)
        return DoseSimulationResponse(
            readings_used=len(points), records=[DoseResponse.model_validate(record) for record in records],
            assumptions={
                'model': 'Simulação didática: dose na pele = fluxo ≥10 MeV × taxa de referência × blindagem × tempo. Não é um modelo de transporte de radiação.',
                'skin_dose_rate_per_pfu_mgy_eq_per_hour': SKIN_DOSE_RATE_PER_PFU,
                'shielding_factor': SHIELDING_FACTOR, 'organ_factor': ORGAN_FACTOR,
                'default_activity': 'iva',
            },
        )

    @staticmethod
    def _activity_at(activities, moment):
        current = [
            activity.activity_type for activity in activities
            if utc(activity.started_at) <= moment and (activity.ended_at is None or utc(activity.ended_at) > moment)
        ]
        return min(current, key=ACTIVITY_PRIORITY.get) if current else 'iva'

    def _flux_series(self, start, end):
        """Maior fluxo ≥10 MeV por horário (entre satélites e fontes), em ordem."""
        rows = self.session.exec(select(ProtonFluxReading.observed_at, func.max(ProtonFluxReading.flux_pfu)).where(
            ProtonFluxReading.energy_channel == FLUX_CHANNEL,
            ProtonFluxReading.observed_at >= start, ProtonFluxReading.observed_at <= end,
        ).group_by(ProtonFluxReading.observed_at).order_by(ProtonFluxReading.observed_at)).all()
        return [(utc(time), flux) for time, flux in rows]

    # --- Fluxo de prótons ------------------------------------------------------------------------

    def list_flux(self, channel, start, end, limit):
        statement = select(ProtonFluxReading).where(ProtonFluxReading.energy_channel == channel)
        if start is not None:
            statement = statement.where(ProtonFluxReading.observed_at >= start)
        if end is not None:
            statement = statement.where(ProtonFluxReading.observed_at <= end)
        rows = self.session.exec(statement.order_by(ProtonFluxReading.observed_at.desc(), ProtonFluxReading.id.desc()).limit(limit)).all()
        return [ProtonFluxReadingResponse.model_validate(row) for row in reversed(rows)]

    def sync_proton_flux(self, swpc: SwpcClient, window: str, check_permission: bool = True):
        if check_permission:
            self._catalog_writer()
        try:
            items = swpc.integral_protons(window)
        except SwpcError as exc:
            raise HTTPException(502, str(exc)) from exc
        parsed = {}
        for item in items:
            reading = parse_swpc_reading(item)
            if reading is not None:
                parsed[reading[:3]] = reading[3]
        stored = alerts = 0
        try:
            if parsed:
                times = [key[0] for key in parsed]
                existing = {
                    (utc(row.observed_at), row.energy_channel, row.satellite): row
                    for row in self.session.exec(select(ProtonFluxReading).where(
                        ProtonFluxReading.source == 'noaa_swpc',
                        ProtonFluxReading.observed_at >= min(times), ProtonFluxReading.observed_at <= max(times),
                    )).all()
                }
                for (observed, channel, satellite), flux in parsed.items():
                    row = existing.get((observed, channel, satellite))
                    if row is None:
                        self.session.add(ProtonFluxReading(observed_at=observed, energy_channel=channel, flux_pfu=flux, satellite=satellite, source='noaa_swpc'))
                        stored += 1
                    elif row.flux_pfu != flux:
                        row.flux_pfu = flux
                        self.session.add(row)
                self.session.flush()
                alerts = self._flux_eva_alerts(min(times), max(times))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return ProtonFluxSyncResponse(fetched_count=len(items), stored_count=stored, skipped_count=len(items) - len(parsed), alerts_created=alerts)

    @transactional
    def simulate_proton_flux(self, payload):
        self._catalog_writer()
        event = self._event_by_activity_id(payload.event_activity_id)
        if event is not None and event.event_type != 'SEP':
            raise HTTPException(422, 'A simulação de fluxo deve partir de um SEP')
        onset = utc(event.start_time) if event else payload.onset
        end = onset + timedelta(hours=payload.duration_hours)
        self.session.exec(delete(ProtonFluxReading).where(
            ProtonFluxReading.source == 'simulation', ProtonFluxReading.energy_channel == FLUX_CHANNEL,
            ProtonFluxReading.observed_at >= onset, ProtonFluxReading.observed_at <= end,
        ))
        steps = int(payload.duration_hours * 60 // payload.step_minutes)
        for index in range(steps + 1):
            hours = index * payload.step_minutes / 60
            self.session.add(ProtonFluxReading(
                observed_at=onset + timedelta(hours=hours), energy_channel=FLUX_CHANNEL, satellite='simulated', source='simulation',
                flux_pfu=round(simulated_flux(hours, payload.peak_pfu, payload.rise_hours, payload.decay_hours), 4),
            ))
        self.session.flush()
        self._flux_eva_alerts(onset, end)
        if event is not None:
            # A severidade do alerta de EVA depende do pico de fluxo.
            self.process_sep(event)
        return ProtonFluxSimulationResponse(
            stored_count=steps + 1, onset=onset, peak_at=onset + timedelta(hours=payload.rise_hours), peak_pfu=payload.peak_pfu,
        )

    def _flux_eva_alerts(self, start, end) -> int:
        """Fluxo ≥10 MeV na escala S1 ou acima durante uma EVA gera alerta."""
        created = 0
        for activity in self._eva_during(start, end):
            eva_start = max(utc(activity.started_at), start)
            eva_end = min(utc(activity.ended_at) or end, end)
            peak = self._peak_flux(eva_start, eva_end)
            severity = flux_severity(peak)
            if severity is None:
                continue
            created += self._raise_alert(
                activity.mission_id, activity.astronaut_id, 'proton_flux_during_eva', f'proton_flux_during_eva:{activity.id}', severity,
                f'Fluxo de prótons ≥10 MeV de {peak:g} pfu durante a EVA iniciada em {utc(activity.started_at):%Y-%m-%d %H:%M} UTC '
                '(escala S da NOAA: S1 a partir de 10 pfu). Avalie encerrar a EVA e levar o tripulante ao abrigo.',
                {'activity_id': activity.id, 'peak_flux_pfu': peak},
            )
        return created

    # --- Linha do tempo ------------------------------------------------------------------------

    def timeline(self, mission_id):
        mission, member, surgeon = self._member(mission_id)
        start = utc(mission.started_at or mission.planned_launch_at)
        end = utc(mission.ended_at) or now()
        events = self.session.exec(select(SpaceWeatherEvent).where(
            SpaceWeatherEvent.start_time <= end,
            func.coalesce(SpaceWeatherEvent.end_time, SpaceWeatherEvent.start_time) >= start,
        ).order_by(SpaceWeatherEvent.start_time, SpaceWeatherEvent.id)).all()

        activities = self.session.exec(select(CrewActivity).where(CrewActivity.mission_id == mission_id).order_by(CrewActivity.started_at, CrewActivity.id)).all()
        clinical_only = None if surgeon else self.user.id if member.role == 'astronaut' else False
        follow_ups, alerts = [], []
        if clinical_only is not False:
            follow_up_query = select(RadiationFollowUp).where(RadiationFollowUp.mission_id == mission_id)
            alert_query = select(RadiationAlert).where(RadiationAlert.mission_id == mission_id, RadiationAlert.status.in_(['open', 'acknowledged']))
            if clinical_only is not None:
                follow_up_query = follow_up_query.where(RadiationFollowUp.astronaut_id == clinical_only)
                alert_query = alert_query.where(RadiationAlert.astronaut_id == clinical_only)
            follow_ups = [self._follow_up_response(row) for row in self.session.exec(follow_up_query.order_by(RadiationFollowUp.opened_at)).all()]
            alerts = [self._alert_response(row, surgeon) for row in self.session.exec(alert_query.order_by(RadiationAlert.created_at)).all()]

        return TimelineResponse(
            mission_id=mission_id, start=start, end=end,
            events=[EventResponse.model_validate(event) for event in events],
            chains=self._chains(events),
            activities=[CrewActivityResponse.model_validate(activity) for activity in activities],
            follow_ups=follow_ups, alerts=alerts, can_view_clinical=clinical_only is not False, can_manage=surgeon,
        )

    def _chains(self, events) -> list[EventChain]:
        """Agrupa FLR, CME e SEP ligados pelo DONKI (em qualquer sentido). Eventos ligados
        fora do período da missão entram na cadeia se estiverem importados."""
        if not events:
            return []
        by_activity = {event.activity_id: event for event in events}
        ids = [event.id for event in events]
        links = self.session.exec(select(SpaceWeatherEventLink, SpaceWeatherEvent.activity_id).join(
            SpaceWeatherEvent, SpaceWeatherEvent.id == SpaceWeatherEventLink.event_id,
        ).where(or_(SpaceWeatherEventLink.event_id.in_(ids), SpaceWeatherEventLink.linked_activity_id.in_(list(by_activity))))).all()
        pairs = [(source, link.linked_activity_id) for link, source in links]
        missing = {target for pair in pairs for target in pair if target not in by_activity}
        if missing:
            for event in self.session.exec(select(SpaceWeatherEvent).where(SpaceWeatherEvent.activity_id.in_(list(missing)))).all():
                by_activity[event.activity_id] = event

        parent = {key: key for key in by_activity}

        def find(key):
            while parent[key] != key:
                parent[key] = parent[parent[key]]
                key = parent[key]
            return key

        others = defaultdict(set)
        for source, target in pairs:
            if source in parent and target in parent:
                parent[find(source)] = find(target)
            elif source in parent:
                others[source].add(target)
            elif target in parent:
                others[target].add(source)

        groups = defaultdict(list)
        for key, event in by_activity.items():
            groups[find(key)].append(event)
        chains = []
        for members in groups.values():
            members.sort(key=lambda item: (utc(item.start_time), item.activity_id))
            if not any(event.id in ids for event in members):
                continue
            pick = lambda kind: [EventResponse.model_validate(event) for event in members if event.event_type == kind]
            chains.append(EventChain(
                flares=pick('FLR'), cmes=pick('CME'), seps=pick('SEP'),
                other_linked=sorted({target for event in members for target in others[event.activity_id]}),
                starts_at=utc(members[0].start_time),
            ))
        chains.sort(key=lambda chain: chain.starts_at)
        return chains
