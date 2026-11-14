from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import aliased
from sqlmodel import select

from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlert
from app.models.notifications import HealthNotification
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from app.schemas.notifications import NotificationResponse
from app.services.health_alert_rules import aware, evaluate_reading
from app.services.preflight_service import PreflightService, transactional


class NotificationService(PreflightService):
    def notify_critical(self, alert, observation):
        if alert.severity != 'critical' or alert.status == 'resolved' or observation.signal_quality == 'poor':
            return 0
        profile = observation.evaluation_profile
        if not profile:
            return 0
        freshness = profile['freshness_minutes'].get(observation.indicator, profile['freshness_minutes']['default'])
        if datetime.now(timezone.utc) - aware(observation.collected_at) > timedelta(minutes=freshness):
            return 0
        if not any(result['rule_id'] == alert.rule_id and result['severity'] == 'critical' for result in evaluate_reading(observation, profile)):
            return 0
        self.session.exec(select(User).where(User.id == alert.astronaut_id).with_for_update()).one()
        self.session.refresh(alert)
        if alert.status == 'resolved':
            return 0
        latest = self.session.exec(select(HealthObservation).where(HealthObservation.astronaut_id == alert.astronaut_id, HealthObservation.indicator == observation.indicator, HealthObservation.signal_quality != 'poor').order_by(HealthObservation.collected_at.desc(), HealthObservation.id.desc())).first()
        if latest is None or latest.id != observation.id:
            return 0
        mission_id = observation.mission_id
        if mission_id is None:
            missions = self.session.exec(select(Mission).join(MissionMember, MissionMember.mission_id == Mission.id).where(MissionMember.user_id == alert.astronaut_id, MissionMember.role == 'astronaut', Mission.ended_at.is_(None))).all()
            if len(missions) != 1:
                self.delivery_note(observation, 'Notificação não direcionada: selecione a missão da coleta para identificar o médico de voo responsável.')
                return 0
            mission_id = missions[0].id
        mission = self.session.get(Mission, mission_id)
        crew = self.session.exec(select(MissionMember).where(MissionMember.mission_id == mission_id, MissionMember.user_id == alert.astronaut_id)).first()
        if mission is None or mission.ended_at is not None or crew is None:
            return 0
        recipients = self.session.exec(select(User).join(MissionMember, MissionMember.user_id == User.id).where(
            MissionMember.mission_id == mission_id, MissionMember.role == 'flight_surgeon',
            User.is_physician == True, User.id != alert.astronaut_id,
        )).all()
        if not recipients:
            self.delivery_note(observation, 'Notificação não direcionada: a missão não possui outro médico com perfil médico e papel de médico de voo.')
        created = 0
        astronaut = self.session.get(User, alert.astronaut_id)
        for recipient in recipients:
            existing = self.session.exec(select(HealthNotification).where(
                HealthNotification.recipient_user_id == recipient.id, HealthNotification.mission_id == mission_id,
                HealthNotification.alert_id == alert.id,
            )).first()
            if existing:
                continue
            self.session.add(HealthNotification(
                recipient_user_id=recipient.id, mission_id=mission_id, alert_id=alert.id,
                observation_id=observation.id, title=f'Alerta crítico · {astronaut.name}',
                message=f'{alert.reason} Verifique o prontuário da missão {mission.name} e siga o protocolo de emergência.',
            ))
            created += 1
        self.session.flush()
        return created

    def delivery_note(self, observation, message):
        if message not in observation.evaluation_notes:
            observation.evaluation_notes = [*observation.evaluation_notes, message]
            self.session.add(observation)

    def visible(self, mission_id=None):
        if not self.user.is_physician:
            raise HTTPException(403, 'As notificações clínicas são destinadas aos médicos de voo')
        doctor = aliased(MissionMember)
        crew = aliased(MissionMember)
        astronaut = aliased(User)
        statement = select(HealthNotification).join(HealthAlert, HealthAlert.id == HealthNotification.alert_id).join(
            doctor, and_(doctor.mission_id == HealthNotification.mission_id, doctor.user_id == self.user.id, doctor.role == 'flight_surgeon'),
        ).join(crew, and_(crew.mission_id == HealthNotification.mission_id, crew.user_id == HealthAlert.astronaut_id)).join(
            astronaut, astronaut.id == HealthAlert.astronaut_id,
        ).where(HealthNotification.recipient_user_id == self.user.id, or_(astronaut.is_astronaut == True, crew.role == 'astronaut'))
        if mission_id is not None:
            statement = statement.where(HealthNotification.mission_id == mission_id)
        return statement

    def response(self, notification):
        alert = self.session.get(HealthAlert, notification.alert_id)
        observation = self.session.get(HealthObservation, notification.observation_id)
        mission = self.session.get(Mission, notification.mission_id)
        astronaut = self.session.get(User, alert.astronaut_id)
        return NotificationResponse(
            id=notification.id, mission_id=mission.id, mission_name=mission.name,
            astronaut_id=astronaut.id, astronaut_name=astronaut.name, alert_id=alert.id,
            indicator=observation.indicator, alert_status=alert.status, title=notification.title,
            message=notification.message, created_at=notification.created_at, collected_at=observation.collected_at,
            read_at=notification.read_at, verification_required=alert.verification_required,
        )

    def list_notifications(self, status, mission_id, page, per_page):
        statement = self.visible(mission_id)
        if status == 'pending':
            statement = statement.where(HealthNotification.read_at.is_(None), HealthAlert.status != 'resolved')
        result = self._page(statement.order_by(HealthNotification.created_at.desc(), HealthNotification.id.desc()), page, per_page)
        result['data'] = [self.response(notification) for notification in result['data']]
        return result

    def summary(self):
        statement = self.visible().where(HealthNotification.read_at.is_(None))
        count = lambda query: self.session.exec(select(func.count()).select_from(query.subquery())).one()
        return {'unread_count': count(statement), 'pending_count': count(statement.where(HealthAlert.status != 'resolved'))}

    @transactional
    def read(self, notification_id):
        notification = self.session.exec(self.visible().where(HealthNotification.id == notification_id)).first()
        if notification is None:
            raise HTTPException(404, 'Notificação não encontrada')
        if notification.read_at is None:
            notification.read_at = datetime.now(timezone.utc)
            self.session.add(notification)
            self.session.flush()
        return self.response(notification)

    @transactional
    def read_all(self):
        notifications = self.session.exec(self.visible().where(HealthNotification.read_at.is_(None))).all()
        now = datetime.now(timezone.utc)
        for notification in notifications:
            notification.read_at = now
            self.session.add(notification)
        self.session.flush()
        return {'marked_count': len(notifications)}
