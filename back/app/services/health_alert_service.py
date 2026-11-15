from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlmodel import select

from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlert, HealthAlertEvent, HealthAlertObservation, HealthAlertSettings
from app.models.preflight import Mission
from app.models.user import User
from app.schemas.health_alerts import AlertEventResponse, AlertResponse
from app.services.health_alert_rules import SEVERITY_RANK, aware, evaluate_reading, evaluate_trend, matches, profile_for, profiles
from app.services.preflight_service import PreflightService, transactional


class HealthAlertService(PreflightService):
    def authorize(self, astronaut_id, mission_id):
        from app.services.health_service import HealthService
        return HealthService(self.session, self.user).authorize(astronaut_id, mission_id)

    def profile(self, mission_id):
        settings = self.session.get(HealthAlertSettings, mission_id) if mission_id is not None else None
        return profile_for(settings)

    def evaluate(self, observation, preserve_previous=False):
        profile = self.profile(observation.mission_id)
        if preserve_previous and observation.evaluation_profile:
            profile['previous_evaluation'] = {'profile': observation.evaluation_profile, 'status': observation.evaluation_status, 'notes': list(observation.evaluation_notes)}
            profile['reassessed_at'] = datetime.now(timezone.utc).isoformat()
        observation.evaluation_profile = profile
        observation.evaluation_status = 'insufficient_quality' if observation.signal_quality == 'poor' else 'evaluated'
        notes = []
        if observation.activity == 'unknown' and observation.indicator in ('heart_rate', 'respiratory_rate'):
            notes.append('Activity context is missing; resting ranges were not applied. Extreme readings require immediate verification.')
        if observation.signal_quality == 'poor':
            notes.append('Insufficient quality. Repeat the measurement; an extreme reading requires immediate verification. Open alerts are preserved.')
        elif observation.signal_quality == 'unknown':
            notes.append('Signal quality not provided.')
        if observation.supplemental_oxygen is True:
            notes.append('On supplemental oxygen.')
        if observation.indicator == 'blood_glucose' and observation.glucose_context not in profile['high_glucose_thresholds']:
            notes.append('No high glucose rule is configured for this meal context. The low glucose rule remains active.')
        observation.evaluation_notes = notes
        self.session.add(observation)
        readings = evaluate_reading(observation, profile)
        if any(rule['indicator'] == observation.indicator for rule in profile['trends']):
            rows = self.session.exec(select(HealthObservation).where(
                HealthObservation.astronaut_id == observation.astronaut_id,
                HealthObservation.mission_id == observation.mission_id,
                HealthObservation.indicator == observation.indicator,
            )).all()
            readings.extend(evaluate_trend(observation, rows, profile))
        active = self.session.exec(select(HealthAlert).where(
            HealthAlert.astronaut_id == observation.astronaut_id,
            HealthAlert.status.in_(['open', 'acknowledged']),
        )).all()
        by_rule = {alert.rule_id: alert for alert in active}
        handled = set()
        for result in readings:
            alert = by_rule.get(result['rule_id'])
            action = 'measurement_added'
            trigger = result['trigger_observation']
            if alert is None:
                alert = HealthAlert(
                    astronaut_id=observation.astronaut_id, mission_id=observation.mission_id,
                    rule_id=result['rule_id'], rule_version=profile['rule_version'], profile_snapshot=profile,
                    indicator=trigger.indicator, severity=result['severity'], reason=result['reason'],
                    verification_required=result['verification_required'], trigger_observation_id=trigger.id,
                )
                self.session.add(alert)
                self.session.flush()
                by_rule[alert.rule_id] = alert
                action = 'created'
            elif SEVERITY_RANK[result['severity']] > SEVERITY_RANK[alert.severity]:
                alert.severity = result['severity']
                alert.status = 'open'
                alert.acknowledged_at = None
                alert.acknowledged_by_user_id = None
                action = 'escalated'
            current_trigger = self.session.get(HealthObservation, alert.trigger_observation_id)
            if action in ('created', 'escalated') or (SEVERITY_RANK[result['severity']] == SEVERITY_RANK[alert.severity] and aware(trigger.collected_at) >= aware(current_trigger.collected_at)):
                alert.reason = result['reason']
                alert.trigger_observation_id = trigger.id
                alert.indicator = trigger.indicator
                alert.rule_version = profile['rule_version']
                alert.profile_snapshot = profile
                alert.verification_required = result['verification_required']
            alert.updated_at = datetime.now(timezone.utc)
            self.session.add(alert)
            sources = {source.id: source for source in [*result['sources'], observation]}
            for source in sources.values():
                self.attach(alert, source, action if source.id == observation.id else 'source_added', result['reason'], profile['rule_version'])
            if result['severity'] == 'critical':
                from app.services.notification_service import NotificationService
                NotificationService(self.session, self.user).notify_critical(alert, trigger)
            handled.add(alert.id)
        for alert in active:
            related = alert.indicator == observation.indicator or (alert.rule_id == 'acute_consciousness' and observation.indicator in ('attention', 'consciousness'))
            if related and alert.id not in handled:
                reason = 'New measurement linked. The alert remains active until a valid reading outside the range or a medical resolution.'
                action = 'measurement_added'
                if observation.signal_quality == 'poor':
                    reason = 'Insufficient quality; the measurement neither closes nor lowers the open alert.'
                elif self.normalizes_rule(alert, observation, profile):
                    if alert.severity == 'critical':
                        reason = 'The new measurement is outside the range that raised the critical alert. The previous event still requires explicit resolution by the flight surgeon.'
                    else:
                        reason = 'Alert closed automatically after a new valid measurement outside the rule range.'
                        alert.status = 'resolved'
                        alert.resolved_at = datetime.now(timezone.utc)
                        alert.resolved_by_user_id = self.user.id
                        alert.resolution_note = reason
                        action = 'auto_resolved'
                self.attach(alert, observation, action, reason, profile['rule_version'])
                alert.updated_at = datetime.now(timezone.utc)
                self.session.add(alert)
        self.session.flush()

    def normalizes_rule(self, alert, observation, profile):
        if observation.indicator != alert.indicator or observation.signal_quality == 'poor':
            return False
        latest = self.session.exec(select(HealthObservation).join(HealthAlertObservation, HealthAlertObservation.observation_id == HealthObservation.id).where(HealthAlertObservation.alert_id == alert.id, HealthObservation.id != observation.id).order_by(HealthObservation.collected_at.desc(), HealthObservation.id.desc())).first()
        if latest and (aware(observation.collected_at), observation.id) <= (aware(latest.collected_at), latest.id):
            return False
        minutes = profile['freshness_minutes'].get(observation.indicator, profile['freshness_minutes']['default'])
        if datetime.now(timezone.utc) - aware(observation.collected_at) > timedelta(minutes=minutes):
            return False
        if alert.rule_id.startswith('resting_') and observation.activity != 'rest':
            return False
        if alert.rule_id.endswith('_verification'):
            return observation.activity == 'rest'
        trend = next((rule for rule in alert.profile_snapshot['trends'] if rule['id'] == alert.rule_id), None)
        if trend:
            return observation.category not in trend['categories'] if 'categories' in trend else not matches(observation.value, trend)
        if alert.rule_id.startswith('high_blood_glucose_'):
            if observation.glucose_context not in profile['high_glucose_thresholds'] or observation.glucose_context not in alert.profile_snapshot['high_glucose_thresholds']:
                return False
            return not any(result['rule_id'].startswith('high_blood_glucose_') for result in [*evaluate_reading(observation, alert.profile_snapshot), *evaluate_reading(observation, profile)])
        return not any(result['rule_id'] == alert.rule_id for result in [*evaluate_reading(observation, alert.profile_snapshot), *evaluate_reading(observation, profile)])

    def attach(self, alert, observation, action, reason, rule_version):
        if self.session.get(HealthAlertObservation, (alert.id, observation.id)) is not None:
            if action == 'auto_resolved':
                self.event(alert, action, reason, observation.id, rule_version)
                self.session.flush()
            return
        self.session.add(HealthAlertObservation(alert_id=alert.id, observation_id=observation.id))
        self.event(alert, action, reason, observation.id, rule_version)
        self.session.flush()

    def event(self, alert, action, reason, observation_id=None, rule_version=None):
        self.session.add(HealthAlertEvent(
            alert_id=alert.id, observation_id=observation_id, actor_user_id=self.user.id,
            action=action, severity=alert.severity, status=alert.status, reason=reason,
            rule_version=rule_version or alert.rule_version,
        ))

    def response(self, alert, can_resolve):
        channel = alert.profile_snapshot.get('emergency_channel')
        if alert.status != 'resolved' and alert.mission_id is not None:
            settings = self.session.get(HealthAlertSettings, alert.mission_id)
            if settings:
                channel = settings.emergency_channel
        message = None
        if alert.severity == 'critical':
            message = 'Follow the emergency protocol and notify the medical team.'
            message += f' Mission channel: {channel}.' if channel else ' Emergency channel not configured; use the mission operational channel.'
        latest = self.session.exec(select(HealthObservation).join(HealthAlertObservation, HealthAlertObservation.observation_id == HealthObservation.id).where(HealthAlertObservation.alert_id == alert.id).order_by(HealthObservation.collected_at.desc(), HealthObservation.id.desc())).first()
        awaiting_review = alert.status != 'resolved' and alert.severity == 'critical' and latest is not None and self.normalizes_rule(alert, latest, self.profile(latest.mission_id))
        data = alert.model_dump()
        data['latest_observation'] = latest
        data['awaiting_medical_review'] = awaiting_review
        data['trigger_observation'] = self._get(HealthObservation, alert.trigger_observation_id)
        data['source_count'] = self.session.exec(select(func.count()).select_from(HealthAlertObservation).where(HealthAlertObservation.alert_id == alert.id)).one()
        data['can_acknowledge'] = alert.status == 'open'
        data['can_resolve'] = can_resolve and alert.status != 'resolved'
        data['emergency_channel'] = channel
        data['protocol_message'] = message
        return AlertResponse.model_validate(data)

    def list_alerts(self, astronaut_id, mission_id, status, page, per_page, indicator=None):
        can_resolve = self.authorize(astronaut_id, mission_id)
        statement = select(HealthAlert).where(HealthAlert.astronaut_id == astronaut_id)
        if mission_id is not None:
            statement = statement.where(HealthAlert.mission_id == mission_id)
        if indicator is not None:
            statement = statement.where(HealthAlert.indicator == indicator)
        if status == 'active':
            statement = statement.where(HealthAlert.status.in_(['open', 'acknowledged']))
        elif status != 'all':
            statement = statement.where(HealthAlert.status == status)
        priority = case((HealthAlert.status == 'resolved', 1), else_=0)
        severity = case((HealthAlert.severity == 'critical', 3), (HealthAlert.severity == 'urgent', 2), else_=1)
        result = self._page(statement.order_by(priority, severity.desc(), HealthAlert.updated_at.desc(), HealthAlert.id.desc()), page, per_page)
        result['data'] = [self.response(alert, can_resolve) for alert in result['data']]
        return result

    def get_alert(self, astronaut_id, mission_id, alert_id):
        can_resolve = self.authorize(astronaut_id, mission_id)
        alert = self._get(HealthAlert, alert_id)
        if alert.astronaut_id != astronaut_id or (mission_id is not None and alert.mission_id != mission_id):
            raise HTTPException(404, 'Alert not found in this medical record')
        return alert, can_resolve

    def history(self, astronaut_id, mission_id, alert_id, page, per_page):
        alert, _ = self.get_alert(astronaut_id, mission_id, alert_id)
        statement = select(HealthAlertEvent).where(HealthAlertEvent.alert_id == alert.id).order_by(HealthAlertEvent.created_at.desc(), HealthAlertEvent.id.desc())
        result = self._page(statement, page, per_page)
        result['data'] = [AlertEventResponse.model_validate({**event.model_dump(), 'observation': self.session.get(HealthObservation, event.observation_id) if event.observation_id else None}) for event in result['data']]
        return result

    @transactional
    def acknowledge(self, astronaut_id, mission_id, alert_id):
        self.authorize(astronaut_id, mission_id)
        self.session.exec(select(User).where(User.id == astronaut_id).with_for_update()).one()
        alert, can_resolve = self.get_alert(astronaut_id, mission_id, alert_id)
        self.session.refresh(alert)
        if alert.status == 'resolved':
            raise HTTPException(409, 'A resolved alert cannot be acknowledged')
        if alert.status == 'open':
            alert.status = 'acknowledged'
            alert.acknowledged_at = datetime.now(timezone.utc)
            alert.acknowledged_by_user_id = self.user.id
            alert.updated_at = alert.acknowledged_at
            self.session.add(alert)
            self.event(alert, 'acknowledged', 'Alert seen. Acknowledging does not mean resolving.')
            self.session.flush()
        return self.response(alert, can_resolve)

    @transactional
    def resolve(self, astronaut_id, mission_id, alert_id, payload):
        if not self.authorize(astronaut_id, mission_id):
            raise HTTPException(403, 'Resolution requires the authorized mission flight surgeon')
        self.session.exec(select(User).where(User.id == astronaut_id).with_for_update()).one()
        alert, _ = self.get_alert(astronaut_id, mission_id, alert_id)
        self.session.refresh(alert)
        if alert.status != 'resolved':
            alert.status = 'resolved'
            alert.resolved_at = datetime.now(timezone.utc)
            alert.resolved_by_user_id = self.user.id
            alert.resolution_note = payload.note
            alert.updated_at = alert.resolved_at
            self.session.add(alert)
            self.event(alert, 'resolved', payload.note)
            self.session.flush()
        return self.response(alert, True)

    def settings(self, mission_id):
        _, actor = self._access(mission_id)
        settings = self.session.get(HealthAlertSettings, mission_id)
        profile = profile_for(settings)
        return {
            'mission_id': mission_id, 'revision': settings.revision if settings else 0,
            'profile_id': settings.profile_id if settings else profile['version'],
            'timezone': profile['timezone'], 'emergency_channel': profile.get('emergency_channel'),
            'oxygen_thresholds': profile['oxygen_thresholds'], 'high_glucose_thresholds': profile['high_glucose_thresholds'],
            'approval_note': settings.approval_note if settings else None,
            'approved_by_user_id': settings.approved_by_user_id if settings else None,
            'can_edit': self.user.is_physician and actor.role in ('flight_surgeon', 'mission_admin'),
            'rule_version': profile['rule_version'],
        }

    @transactional
    def update_settings(self, mission_id, payload):
        self._require_physician()
        self._access(mission_id, {'flight_surgeon', 'mission_admin'}, lock=True)
        settings = self.session.get(HealthAlertSettings, mission_id)
        revision = settings.revision if settings else 0
        if revision != payload.expected_revision:
            raise HTTPException(409, 'The configuration was changed; refresh the screen before saving')
        settings = settings or HealthAlertSettings(mission_id=mission_id)
        values = payload.model_dump(exclude={'expected_revision'})
        if 'high_glucose_thresholds' not in payload.model_fields_set:
            values['high_glucose_thresholds'] = settings.high_glucose_thresholds if revision else profiles()['profiles'][payload.profile_id]['high_glucose_thresholds']
        for key, value in values.items():
            setattr(settings, key, value)
        settings.revision = revision + 1
        settings.approved_by_user_id = self.user.id
        settings.updated_at = datetime.now(timezone.utc)
        self.session.add(settings)
        self.session.flush()
        return self.settings(mission_id)
