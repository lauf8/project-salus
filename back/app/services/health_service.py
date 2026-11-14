from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from app.models.health import HealthObservation
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from app.schemas.health import HealthSummary, IndicatorSummary, UNITS
from app.services.health_alert_rules import aware
from app.services.preflight_service import transactional


class HealthService:
    def __init__(self, session: Session, user: User):
        self.session = session
        self.user = user

    def context(self):
        memberships = self.session.exec(select(MissionMember).where(MissionMember.user_id == self.user.id)).all()
        is_astronaut = self.user.is_astronaut or any(member.role == 'astronaut' for member in memberships)
        supervised = []
        if self.user.is_physician or self.user.is_nurse:
            mission_ids = [member.mission_id for member in memberships if (member.role == 'flight_surgeon' and self.user.is_physician) or (member.role == 'nurse' and self.user.is_nurse)]
            if mission_ids:
                records = self.session.exec(select(User, MissionMember, Mission).join(
                    MissionMember, MissionMember.user_id == User.id,
                ).join(Mission, Mission.id == MissionMember.mission_id).where(
                    Mission.id.in_(mission_ids), User.id != self.user.id,
                    MissionMember.role == 'astronaut',
                ).order_by(Mission.id, User.name)).all()
                supervised = [{'id': user.id, 'name': user.name, 'mission_id': mission.id, 'mission_name': mission.name} for user, member, mission in records]
        can_manage_catalog = self.user.is_global_admin or self.user.is_physician and any(member.role in ('mission_admin', 'flight_surgeon') for member in memberships)
        return {'is_astronaut': is_astronaut, 'supervised_astronauts': supervised, 'can_manage_catalog': can_manage_catalog, 'can_manage_spacecraft': can_manage_catalog or self.user.is_mission_admin and any(m.role == 'mission_admin' for m in memberships), 'can_manage_food_catalog': can_manage_catalog or self.user.is_nutritionist and any(m.role == 'nutritionist' for m in memberships), 'can_create_mission': self.user.is_global_admin or self.user.is_mission_admin or self.user.is_physician, 'can_manage_users': self.user.is_global_admin}

    def authorize(self, astronaut_id, mission_id=None):
        target = self.session.get(User, astronaut_id)
        memberships = self.session.exec(select(MissionMember).where(MissionMember.user_id == astronaut_id)).all()
        if target is None or not (target.is_astronaut or any(m.role == 'astronaut' for m in memberships)):
            raise HTTPException(404, 'Astronauta não encontrado')
        if mission_id is not None:
            if self.session.get(Mission, mission_id) is None or not any(m.mission_id == mission_id and m.role == 'astronaut' for m in memberships):
                raise HTTPException(404, 'Vínculo do astronauta com a missão não encontrado')
        if self.user.id == astronaut_id:
            return False
        if not (self.user.is_physician or self.user.is_nurse) or mission_id is None:
            raise HTTPException(403, 'Acesso não autorizado aos dados deste astronauta')
        assessor = self.session.exec(select(MissionMember).where(
            MissionMember.user_id == self.user.id, MissionMember.mission_id == mission_id,
            MissionMember.role.in_(['flight_surgeon', 'nurse']),
        )).first()
        if assessor is None or not (assessor.role == 'flight_surgeon' and self.user.is_physician or assessor.role == 'nurse' and self.user.is_nurse):
            raise HTTPException(403, 'Somente o médico de voo desta missão pode avaliar o astronauta')
        return assessor.role == 'flight_surgeon' and self.user.is_physician

    @transactional
    def create(self, astronaut_id, payload):
        assessor = self.authorize(astronaut_id, payload.mission_id)
        if payload.indicator == 'consciousness' and not assessor:
            raise HTTPException(403, 'A avaliação AVPU deve ser registrada por outro médico autorizado')
        if payload.is_preflight_reference:
            if not assessor:
                raise HTTPException(403, 'A referência pré-missão deve ser registrada por outro médico autorizado')
            mission = self.session.get(Mission, payload.mission_id)
            boundary = mission.started_at or mission.planned_launch_at
            if payload.collected_at >= boundary:
                raise HTTPException(422, 'A referência deve ter sido coletada antes do início da missão')
        self.session.exec(select(User).where(User.id == astronaut_id).with_for_update()).one()
        values = payload.model_dump()
        values['client_request_id'] = str(payload.client_request_id) if payload.client_request_id else None
        submission = payload.model_dump(mode='json', exclude={'client_request_id'})
        submission['original_values'] = payload._original_values
        submission['actor_user_id'] = self.user.id
        submission_hash = sha256(json.dumps(submission, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if payload.client_request_id:
            previous = self.session.exec(select(HealthObservation).where(HealthObservation.astronaut_id == astronaut_id, HealthObservation.client_request_id == str(payload.client_request_id))).first()
            if previous:
                if previous.submission_hash != submission_hash:
                    raise HTTPException(409, 'A chave de reenvio já foi usada com outra medição')
                return previous
        previous = self.session.exec(select(HealthObservation).where(HealthObservation.astronaut_id == astronaut_id, HealthObservation.submission_hash == submission_hash)).first()
        if previous:
            return previous
        observation = HealthObservation(
            **values, astronaut_id=astronaut_id, recorded_by_user_id=self.user.id,
            original_values=payload._original_values, submission_hash=submission_hash,
        )
        self.session.add(observation)
        self.session.flush()
        from app.services.health_alert_service import HealthAlertService
        HealthAlertService(self.session, self.user).evaluate(observation)
        return observation

    def statement(self, astronaut_id, mission_id=None):
        statement = select(HealthObservation).where(HealthObservation.astronaut_id == astronaut_id)
        if mission_id is not None:
            statement = statement.where(HealthObservation.mission_id == mission_id)
        return statement

    def history(self, astronaut_id, indicator, mission_id, start, end, page, per_page):
        self.authorize(astronaut_id, mission_id)
        if start > end:
            raise HTTPException(422, 'O início do período deve ser anterior ao fim')
        statement = self.statement(astronaut_id, mission_id).where(
            HealthObservation.indicator == indicator,
            HealthObservation.collected_at >= start,
            HealthObservation.collected_at <= end,
        )
        total = self.session.exec(select(func.count()).select_from(statement.subquery())).one()
        rows = self.session.exec(statement.order_by(
            HealthObservation.collected_at, HealthObservation.recorded_at, HealthObservation.id,
        ).offset((page - 1) * per_page).limit(per_page)).all()
        return {'data': rows, 'pagination': {
            'page': page, 'per_page': per_page, 'total': total,
            'total_pages': (total + per_page - 1) // per_page,
            'has_next': page * per_page < total, 'has_previous': page > 1,
        }}

    def delta(self, latest, comparison):
        if latest is None or comparison is None or latest.indicator in ('consciousness', 'attention'):
            return None
        keys = ('systolic', 'diastolic') if latest.indicator == 'blood_pressure' else ('value',)
        return {key: round(getattr(latest, key) - getattr(comparison, key), 3) for key in keys}

    def summary(self, astronaut_id, mission_id):
        assessor = self.authorize(astronaut_id, mission_id)
        indicators = []
        from app.services.health_alert_service import HealthAlertService
        profile = HealthAlertService(self.session, self.user).profile(mission_id)
        for indicator, unit in UNITS.items():
            statement = self.statement(astronaut_id, mission_id).where(HealthObservation.indicator == indicator)
            rows = self.session.exec(statement.order_by(
                HealthObservation.collected_at.desc(), HealthObservation.recorded_at.desc(), HealthObservation.id.desc(),
            ).limit(5)).all()
            latest = rows[0] if rows else None
            previous = rows[1] if len(rows) > 1 else None
            reference_mission = mission_id if mission_id is not None else latest.mission_id if latest else None
            reference = None
            if reference_mission is not None and latest is not None:
                mission = self.session.get(Mission, reference_mission)
                boundary = mission.started_at or mission.planned_launch_at
                reference = self.session.exec(statement.where(
                    HealthObservation.mission_id == reference_mission,
                    HealthObservation.is_preflight_reference == True,
                    HealthObservation.collected_at < boundary,
                    HealthObservation.collected_at <= latest.collected_at,
                ).order_by(HealthObservation.collected_at.desc(), HealthObservation.recorded_at.desc(), HealthObservation.id.desc()).limit(1)).first()
            previous_delta = self.delta(latest, previous)
            trend = None
            if previous_delta is not None:
                values = list(previous_delta.values())
                trend = 'stable' if all(v == 0 for v in values) else 'increasing' if all(v >= 0 for v in values) else 'decreasing' if all(v <= 0 for v in values) else 'mixed'
            status = 'no_measurement'
            notes = []
            if latest:
                status = latest.evaluation_status
                notes = list(latest.evaluation_notes)
                freshness = profile['freshness_minutes'].get(indicator, profile['freshness_minutes']['default'])
                if datetime.now(timezone.utc) - aware(latest.collected_at) > timedelta(minutes=freshness):
                    status = 'stale'
                    notes.append('Medição desatualizada para a janela configurada; registre uma nova leitura.')
            indicators.append(IndicatorSummary(
                indicator=indicator, unit=unit, latest=latest, previous=previous,
                measurement_status=status, evaluation_notes=notes,
                preflight_reference=reference, previous_delta=previous_delta,
                reference_delta=self.delta(latest, reference), trend=trend,
                sequence=list(reversed(rows)) if indicator in ('consciousness', 'attention') else [],
            ))
        return HealthSummary(
            astronaut_id=astronaut_id, mission_id=mission_id, can_record=True,
            can_record_consciousness=assessor, can_set_reference=assessor, indicators=indicators,
        )
