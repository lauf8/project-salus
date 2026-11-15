from collections import Counter
from datetime import timedelta
from hashlib import sha256
import json

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models.access import AccessAuditEvent
from app.models.predictive import FeatureSnapshot, PredictionModel, PredictionRun, RecommendationAction, RecommendationEvent, RecommendationFeedback, RecommendationOutcome, RiskPrediction
from app.models.preflight import Mission, MissionMember, utc_now
from app.models.spacecraft import Spacecraft
from app.models.user import User
from app.services.predictive.config import ENGINE_VERSION, manual_cooldown_seconds, maximum_attempts, rules_config, schedule_hours
from app.services.predictive.data_collection import AstronautDataCollector, mission_status_at
from app.services.predictive.features import aware
from app.services.predictive.health_risk import HealthRiskPredictionService
from app.services.predictive.knowledge import PredictiveKnowledgeService
from app.services.predictive.mission_risk import MissionRiskPredictionService, SpacecraftRiskPredictionService
from app.services.predictive.recommendations import RecommendationEngine, sync_catalog


CLINICAL_DOMAINS = {'cardiovascular', 'sleep', 'nutrition', 'musculoskeletal', 'other'}
ALL_DOMAINS = CLINICAL_DOMAINS | {'psychological'}
ROLE_PROFILE = {'flight_surgeon': 'is_physician', 'nurse': 'is_nurse', 'psychologist': 'is_psychologist', 'nutritionist': 'is_nutritionist', 'mission_admin': None, 'astronaut': None}
ROLE_DOMAINS = {'flight_surgeon': CLINICAL_DOMAINS, 'nurse': CLINICAL_DOMAINS, 'psychologist': {'psychological'}, 'nutritionist': {'nutrition'}}
SERIES_DOMAIN = {name: settings['domain'] for name, settings in rules_config()['indicators'].items()}
KIND_LABEL = {'rule': 'Rule-based risk', 'anomaly': 'Statistical anomaly', 'ml': 'Machine learning prediction', 'insufficient_data': 'Insufficient information'}


def jsonable(value):
    return json.loads(json.dumps(value, default=str))


class PredictiveService:
    def __init__(self, session, user, rag=None):
        self.session = session
        self.user = user
        self.rag = rag

    def membership(self, mission_id, user_id=None):
        return self.session.exec(select(MissionMember).where(MissionMember.mission_id == mission_id, MissionMember.user_id == (user_id or self.user.id))).first()

    def role_active(self, member):
        if member is None:
            return False
        profile = ROLE_PROFILE.get(member.role)
        return profile is None or bool(getattr(self.user, profile))

    def astronaut_mission(self, astronaut_id, mission_id=None):
        rows = self.session.exec(select(MissionMember, Mission).join(Mission, Mission.id == MissionMember.mission_id).where(MissionMember.user_id == astronaut_id, MissionMember.role == 'astronaut')).all()
        if not rows:
            raise HTTPException(404, 'Astronaut not found')
        if mission_id is not None:
            if not any(mission.id == mission_id for _, mission in rows):
                raise HTTPException(404, 'Astronaut is not assigned to this mission')
            return mission_id
        rank = {'in_progress': 0, 'planned': 1, 'completed': 2}
        rows.sort(key=lambda row: (rank.get(row[1].status, 3), -aware(row[1].planned_launch_at).timestamp()))
        return rows[0][1].id

    def astronaut_domains(self, astronaut_id, mission_id):
        if self.user.id == astronaut_id:
            return set(ALL_DOMAINS)
        member = self.membership(mission_id)
        if member is None or not self.role_active(member) or member.role not in ROLE_DOMAINS:
            raise HTTPException(403, 'Access to this astronaut predictive health data is not authorized')
        return set(ROLE_DOMAINS[member.role])

    def mission_access(self, mission_id):
        mission = self.session.get(Mission, mission_id)
        if mission is None:
            raise HTTPException(404, 'Mission not found')
        member = self.membership(mission_id)
        if member is None and not self.user.is_global_admin:
            raise HTTPException(404, 'Mission not found')
        return mission, member

    def require_global_admin(self):
        if not self.user.is_global_admin:
            raise HTTPException(403, 'Model training, approval and publication require a global administrator')

    def audit(self, resource_type, resource_id, action, fields=None):
        self.session.add(AccessAuditEvent(actor_user_id=self.user.id, resource_type=resource_type, resource_id=resource_id, action=action, changed_fields=fields or []))

    def check_cooldown(self, subject_type, subject_id):
        cooldown = manual_cooldown_seconds()
        if not cooldown:
            return
        recent = self.session.exec(select(PredictionRun).where(PredictionRun.subject_type == subject_type, PredictionRun.subject_id == subject_id, PredictionRun.trigger == 'manual',
                                                               PredictionRun.started_at > utc_now() - timedelta(seconds=cooldown))).first()
        if recent is not None:
            raise HTTPException(429, f'A manual analysis ran less than {cooldown} seconds ago; use the latest result or wait', headers={'Retry-After': str(cooldown)})

    def model_versions(self):
        models = self.session.exec(select(PredictionModel).where(PredictionModel.status == 'active')).all()
        return {'rules': rules_config()['version'], 'catalog': [action.code + ':' + str(action.version) for action in RecommendationEngine(self.session).approved_actions()],
                'models': sorted(f'{model.name}:{model.version}' for model in models)}

    def execute(self, subject_type, subject_id, mission_id, as_of, fingerprint, features, quality, predictions, context, trigger, actor_id):
        versions = self.model_versions()
        bucket = int(as_of.timestamp() // (schedule_hours() * 3600))
        key = sha256(json.dumps([subject_type, subject_id, mission_id, fingerprint, versions, ENGINE_VERSION, bucket], sort_keys=True).encode()).hexdigest()
        existing = self.session.exec(select(PredictionRun).where(PredictionRun.idempotency_key == key)).first()
        if existing is not None and existing.status in ('completed', 'running'):
            return existing, False
        if existing is not None and existing.attempts >= maximum_attempts():
            return existing, False
        if existing is None and trigger == 'scheduled':
            previous = self.latest_run(subject_type, subject_id, mission_id)
            snapshot = self.session.get(FeatureSnapshot, previous.feature_snapshot_id) if previous and previous.feature_snapshot_id else None
            if snapshot is not None and snapshot.input_fingerprint != fingerprint:
                trigger = 'new_data'
        run = existing or PredictionRun(subject_type=subject_type, subject_id=subject_id, mission_id=mission_id, as_of=as_of, engine_version=ENGINE_VERSION,
                                        model_versions=versions, trigger=trigger, idempotency_key=key, attempts=0, requested_by_user_id=actor_id)
        run.attempts += 1
        run.status = 'running'
        run.error = None
        self.session.add(run)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            return self.session.exec(select(PredictionRun).where(PredictionRun.idempotency_key == key)).one(), False
        try:
            with self.session.begin_nested():
                snapshot = self.session.exec(select(FeatureSnapshot).where(FeatureSnapshot.subject_type == subject_type, FeatureSnapshot.subject_id == subject_id, FeatureSnapshot.as_of == as_of,
                                                                           FeatureSnapshot.feature_set_version == rules_config()['feature_set_version'], FeatureSnapshot.input_fingerprint == fingerprint)).first()
                if snapshot is None:
                    snapshot = FeatureSnapshot(subject_type=subject_type, subject_id=subject_id, mission_id=mission_id, as_of=as_of, feature_set_version=rules_config()['feature_set_version'],
                                               input_fingerprint=fingerprint, features=jsonable(features), quality=jsonable(quality), source_references=jsonable({'context': context}))
                    self.session.add(snapshot)
                    self.session.flush()
                run.feature_snapshot_id = snapshot.id
                run.horizon_hours = max((p.get('horizon_hours') or 0 for p in predictions), default=None) or None
                self.store_predictions(run, predictions, context, subject_type, subject_id, mission_id)
                run.status = 'completed'
                run.finished_at = utc_now()
                self.session.add(run)
                self.session.flush()
        except Exception as exc:
            run.status = 'failed'
            run.error = str(exc)[:1000]
            run.finished_at = utc_now()
            self.session.add(run)
            self.session.flush()
        return run, True

    def store_predictions(self, run, predictions, context, subject_type, subject_id, mission_id):
        engine = RecommendationEngine(self.session)
        actions = engine.approved_actions()
        history = engine.outcome_history(run.as_of)
        suggested = set()
        for payload in predictions:
            payload = jsonable(payload)
            model_id = payload.pop('model_id', None)
            selected, excluded = engine.recommend(payload, context, actions, history)
            payload['evidence'] = {**payload.get('evidence', {}), 'excluded_actions': excluded}
            prediction = RiskPrediction(run_id=run.id, model_id=model_id, explanation={'state': 'pending' if selected else 'not_required'}, **payload)
            self.session.add(prediction)
            self.session.flush()
            for rank, row in enumerate(selected, 1):
                action = row['action']
                suggested.add(action.id)
                open_event = self.session.exec(select(RecommendationEvent).where(RecommendationEvent.subject_type == subject_type, RecommendationEvent.subject_id == subject_id,
                                                                                RecommendationEvent.action_id == action.id, RecommendationEvent.status.in_(['pending', 'accepted']))).first()
                if open_event is not None:
                    prediction.evidence = {**prediction.evidence, 'existing_recommendation_ids': [*prediction.evidence.get('existing_recommendation_ids', []), open_event.id]}
                    continue
                self.session.add(RecommendationEvent(prediction_id=prediction.id, action_id=action.id, subject_type=subject_type, subject_id=subject_id, mission_id=mission_id,
                                                     rationale=row['rationale'], rank_score=row['score'], ranking={**row['components'], 'rank': rank}, priority=action.priority,
                                                     urgency=row['urgency'], explanation={'state': 'pending'}))
                self.session.flush()
        stale = self.session.exec(select(RecommendationEvent).where(RecommendationEvent.subject_type == subject_type, RecommendationEvent.subject_id == subject_id, RecommendationEvent.status == 'pending')).all()
        for event in stale:
            if event.action_id not in suggested:
                event.status = 'superseded'
                event.updated_at = utc_now()
                self.session.add(event)

    def finish(self, run, created):
        if created:
            self.session.commit()
            self.session.refresh(run)
        if run.status == 'failed':
            raise HTTPException(503, 'The predictive analysis failed and was recorded for retry; existing clinical records and alerts are unaffected')
        return run

    def analyze_astronaut(self, astronaut_id, mission_id=None, trigger='manual'):
        mission_id = self.astronaut_mission(astronaut_id, mission_id)
        if trigger == 'manual':
            self.astronaut_domains(astronaut_id, mission_id)
            self.check_cooldown('astronaut', astronaut_id)
        sync_catalog(self.session)
        as_of = utc_now()
        service = HealthRiskPredictionService(self.session)
        records, context, fingerprint = service.collect(astronaut_id, mission_id, as_of)
        features, quality, predictions = service.predict(records, context, as_of)
        run, created = self.execute('astronaut', astronaut_id, mission_id, as_of, fingerprint, features, quality, predictions, context, trigger, self.user.id if self.user else None)
        if created and trigger == 'manual':
            self.audit('prediction_runs', run.id, 'analyze_astronaut')
        return self.finish(run, created)

    def analyze_mission(self, mission_id, trigger='manual'):
        mission, member = self.mission_access(mission_id) if trigger == 'manual' else (self.session.get(Mission, mission_id), None)
        if trigger == 'manual':
            if not (self.user.is_global_admin or member and self.role_active(member) and member.role in {'mission_admin', 'flight_surgeon', 'nutritionist'}):
                raise HTTPException(403, 'Only the mission administrator, flight surgeon or nutritionist can request a mission analysis')
            self.check_cooldown('mission', mission_id)
        sync_catalog(self.session)
        as_of = utc_now()
        service = MissionRiskPredictionService(self.session)
        data, fingerprint = service.collect(mission_id, as_of)
        predictions, context = service.predict(data, as_of)
        engine_context = {'mission_status': mission_status_at(mission, as_of), 'mission_id': mission_id, 'active_clinical_alerts': []}
        run, created = self.execute('mission', mission_id, mission_id, as_of, fingerprint, {'mission': context}, {}, predictions, engine_context, trigger, self.user.id if self.user else None)
        if created and trigger == 'manual':
            self.audit('prediction_runs', run.id, 'analyze_mission')
        return self.finish(run, created)

    def analyze_spacecraft(self, spacecraft_id, trigger='manual'):
        if self.session.get(Spacecraft, spacecraft_id) is None:
            raise HTTPException(404, 'Spacecraft not found')
        sync_catalog(self.session)
        as_of = utc_now()
        service = SpacecraftRiskPredictionService(self.session)
        data, fingerprint = service.collect_spacecraft(spacecraft_id, as_of)
        predictions, context = service.predict_spacecraft(data, as_of)
        run, created = self.execute('spacecraft', spacecraft_id, None, as_of, fingerprint, {'spacecraft': context}, {}, predictions, {'mission_status': None}, trigger, self.user.id if self.user else None)
        return self.finish(run, created)

    def latest_run(self, subject_type, subject_id, mission_id=None):
        statement = select(PredictionRun).where(PredictionRun.subject_type == subject_type, PredictionRun.subject_id == subject_id, PredictionRun.status == 'completed')
        if mission_id is not None:
            statement = statement.where(PredictionRun.mission_id == mission_id)
        return self.session.exec(statement.order_by(PredictionRun.as_of.desc(), PredictionRun.id.desc())).first()

    def prediction_response(self, prediction):
        values = prediction.model_dump()
        values['kind_label'] = KIND_LABEL[prediction.prediction_kind]
        values['probability_valid'] = prediction.calibrated_probability is not None and prediction.prediction_kind == 'ml'
        return values

    def run_response(self, run, domains=None):
        if run is None:
            return None
        predictions = self.session.exec(select(RiskPrediction).where(RiskPrediction.run_id == run.id).order_by(RiskPrediction.id)).all()
        if domains is not None:
            predictions = [p for p in predictions if p.domain in domains]
        return {'id': run.id, 'as_of': run.as_of, 'status': run.status, 'trigger': run.trigger, 'engine_version': run.engine_version, 'model_versions': run.model_versions,
                'horizon_hours': run.horizon_hours, 'attempts': run.attempts, 'feature_snapshot_id': run.feature_snapshot_id,
                'predictions': [self.prediction_response(p) for p in predictions]}

    def run_history(self, subject_type, subject_id, domains=None, limit=30):
        runs = self.session.exec(select(PredictionRun).where(PredictionRun.subject_type == subject_type, PredictionRun.subject_id == subject_id).order_by(PredictionRun.as_of.desc(), PredictionRun.id.desc()).limit(limit)).all()
        result = []
        for run in runs:
            predictions = self.session.exec(select(RiskPrediction).where(RiskPrediction.run_id == run.id)).all()
            if domains is not None:
                predictions = [p for p in predictions if p.domain in domains]
            result.append({'id': run.id, 'as_of': run.as_of, 'status': run.status, 'trigger': run.trigger, 'error': run.error if run.status == 'failed' else None,
                           'signals': sum(1 for p in predictions if p.prediction_kind != 'insufficient_data'), 'levels': dict(Counter(p.risk_level for p in predictions)),
                           'kinds': dict(Counter(p.prediction_kind for p in predictions))})
        return result

    def astronaut_view(self, astronaut_id, mission_id=None):
        mission_id = self.astronaut_mission(astronaut_id, mission_id)
        domains = self.astronaut_domains(astronaut_id, mission_id)
        run = self.latest_run('astronaut', astronaut_id, mission_id)
        snapshot = self.session.get(FeatureSnapshot, run.feature_snapshot_id) if run and run.feature_snapshot_id else None
        indicators = {name: values for name, values in (snapshot.features if snapshot else {}).items() if SERIES_DOMAIN.get(name) in domains}
        for values in indicators.values():
            values.pop('source_references', None)
        return {'astronaut_id': astronaut_id, 'mission_id': mission_id, 'visible_domains': sorted(domains), 'latest': self.run_response(run, domains),
                'indicators': indicators, 'data_quality': {name: state for name, state in (snapshot.quality.get('series', {}) if snapshot else {}).items() if name in indicators},
                'timeline': self.timeline(astronaut_id, mission_id, domains), 'history': self.run_history('astronaut', astronaut_id, domains),
                'recommendations': self.recommendations_for('astronaut', astronaut_id, domains), 'notice': self.notice()}

    def timeline(self, astronaut_id, mission_id, domains, days=30):
        now = utc_now()
        records, _ = AstronautDataCollector(self.session).collect(astronaut_id, mission_id, now)
        start = now - timedelta(days=days)
        series = {}
        for record in records:
            if SERIES_DOMAIN.get(record.series) not in domains or aware(record.at) <= start:
                continue
            series.setdefault(record.series, []).append({'at': aware(record.at).isoformat(), 'value': record.value, 'preflight_reference': record.is_preflight_reference})
        return {name: sorted(points, key=lambda point: point['at']) for name, points in series.items()}

    def mission_view(self, mission_id):
        mission, member = self.mission_access(mission_id)
        run = self.latest_run('mission', mission_id)
        snapshot = self.session.get(FeatureSnapshot, run.feature_snapshot_id) if run and run.feature_snapshot_id else None
        can_analyze = self.user.is_global_admin or bool(member and self.role_active(member) and member.role in {'mission_admin', 'flight_surgeon', 'nutritionist'})
        return {'mission_id': mission_id, 'mission_name': mission.name, 'mission_status': mission.status, 'latest': self.run_response(run),
                'context': snapshot.features.get('mission') if snapshot else None, 'history': self.run_history('mission', mission_id),
                'recommendations': self.recommendations_for('mission', mission_id), 'crew_pending_recommendations': self.crew_pending(mission_id),
                'can_analyze': can_analyze, 'notice': self.notice()}

    def crew_pending(self, mission_id):
        rows = self.session.exec(select(RecommendationEvent).where(RecommendationEvent.subject_type == 'astronaut', RecommendationEvent.mission_id == mission_id, RecommendationEvent.status == 'pending')).all()
        return {'count': len(rows), 'by_urgency': dict(Counter(row.urgency for row in rows))}

    def spacecraft_view(self, spacecraft_id):
        if self.session.get(Spacecraft, spacecraft_id) is None:
            raise HTTPException(404, 'Spacecraft not found')
        run = self.latest_run('spacecraft', spacecraft_id)
        snapshot = self.session.get(FeatureSnapshot, run.feature_snapshot_id) if run and run.feature_snapshot_id else None
        return {'spacecraft_id': spacecraft_id, 'latest': self.run_response(run), 'context': snapshot.features.get('spacecraft') if snapshot else None,
                'history': self.run_history('spacecraft', spacecraft_id), 'recommendations': self.recommendations_for('spacecraft', spacecraft_id), 'notice': self.notice()}

    def notice(self):
        return ('Predictive results are preventive attention indicators for human review. They are not diagnoses, do not replace or lower clinical alerts, '
                'and probabilities appear only for validated, calibrated models.')

    def event_domain(self, event):
        prediction = self.session.get(RiskPrediction, event.prediction_id)
        return prediction.domain if prediction else None

    def can_view_event(self, event):
        if event.subject_type == 'spacecraft':
            return True
        if event.subject_type == 'mission':
            return self.user.is_global_admin or self.membership(event.mission_id) is not None
        try:
            domains = self.astronaut_domains(event.subject_id, event.mission_id)
        except HTTPException:
            return False
        return self.event_domain(event) in domains

    def can_decide(self, event, action):
        if event.subject_type == 'spacecraft':
            return self.user.is_global_admin
        if event.mission_id is None:
            return False
        member = self.membership(event.mission_id)
        if self.user.is_global_admin and 'mission_admin' in action.responsible_roles:
            return True
        return bool(member and self.role_active(member) and member.role in action.responsible_roles and self.can_view_event(event))

    def event_response(self, event):
        action = self.session.get(RecommendationAction, event.action_id)
        prediction = self.session.get(RiskPrediction, event.prediction_id)
        feedback = self.session.exec(select(RecommendationFeedback).where(RecommendationFeedback.recommendation_id == event.id).order_by(RecommendationFeedback.id)).all()
        outcomes = self.session.exec(select(RecommendationOutcome).where(RecommendationOutcome.recommendation_id == event.id).order_by(RecommendationOutcome.id)).all()
        return {**event.model_dump(), 'action': action.model_dump(), 'prediction': self.prediction_response(prediction) if prediction else None,
                'feedback': [row.model_dump() for row in feedback], 'outcomes': [row.model_dump() for row in outcomes], 'can_decide': self.can_decide(event, action)}

    def recommendations_for(self, subject_type, subject_id, domains=None):
        events = self.session.exec(select(RecommendationEvent).where(RecommendationEvent.subject_type == subject_type, RecommendationEvent.subject_id == subject_id).order_by(RecommendationEvent.created_at.desc(), RecommendationEvent.id.desc()).limit(100)).all()
        if domains is not None:
            events = [event for event in events if self.event_domain(event) in domains]
        events.sort(key=lambda event: (event.status not in ('pending', 'accepted'), -event.rank_score, -event.id))
        return [self.event_response(event) for event in events]

    def list_recommendations(self, status=None, mission_id=None, limit=100):
        statement = select(RecommendationEvent)
        if status:
            statement = statement.where(RecommendationEvent.status == status)
        if mission_id:
            statement = statement.where(RecommendationEvent.mission_id == mission_id)
        events = self.session.exec(statement.order_by(RecommendationEvent.created_at.desc(), RecommendationEvent.id.desc()).limit(500)).all()
        return [self.event_response(event) for event in events if self.can_view_event(event)][:limit]

    def visible_event(self, recommendation_id):
        event = self.session.get(RecommendationEvent, recommendation_id)
        if event is None or not self.can_view_event(event):
            raise HTTPException(404, 'Recommendation not found')
        return event

    def recommendation(self, recommendation_id):
        return self.event_response(self.visible_event(recommendation_id))

    def feedback(self, recommendation_id, payload):
        event = self.session.exec(select(RecommendationEvent).where(RecommendationEvent.id == recommendation_id).with_for_update()).first()
        if event is None or not self.can_view_event(event):
            raise HTTPException(404, 'Recommendation not found')
        action = self.session.get(RecommendationAction, event.action_id)
        if not self.can_decide(event, action):
            raise HTTPException(403, 'Only a team member responsible for this action can record a decision')
        allowed = {'accepted': {'pending'}, 'rejected': {'pending', 'accepted'}, 'executed': {'accepted'}}
        if event.status not in allowed[payload.decision]:
            raise HTTPException(409, f'A {event.status} recommendation cannot be marked as {payload.decision}')
        now = utc_now()
        self.session.add(RecommendationFeedback(recommendation_id=event.id, user_id=self.user.id, decision=payload.decision, justification=payload.justification, executed_action=payload.executed_action))
        event.status = payload.decision
        event.decided_by_user_id = self.user.id
        event.decided_at = now
        event.updated_at = now
        self.session.add(event)
        self.audit('recommendation_events', event.id, f'feedback_{payload.decision}')
        self.session.commit()
        self.session.refresh(event)
        return self.event_response(event)

    def outcome(self, recommendation_id, payload):
        event = self.visible_event(recommendation_id)
        action = self.session.get(RecommendationAction, event.action_id)
        if not self.can_decide(event, action):
            raise HTTPException(403, 'Only a team member responsible for this action can record an outcome')
        if event.status not in ('accepted', 'executed'):
            raise HTTPException(409, 'Outcomes are recorded for accepted or executed recommendations')
        self.session.add(RecommendationOutcome(recommendation_id=event.id, recorded_by_user_id=self.user.id, **payload.model_dump()))
        self.audit('recommendation_events', event.id, 'outcome_recorded')
        self.session.commit()
        return self.event_response(event)

    def fill_evidence(self, event):
        prediction = self.session.get(RiskPrediction, event.prediction_id)
        action = self.session.get(RecommendationAction, event.action_id)
        evidence = PredictiveKnowledgeService(self.session, self.rag).evidence(prediction.model_dump(), action)
        event.sources = evidence['sources']
        event.explanation = {key: value for key, value in evidence.items() if key != 'sources'} | {'retrieved_at': utc_now().isoformat()}
        event.updated_at = utc_now()
        self.session.add(event)
        if prediction.explanation.get('state') == 'pending':
            prediction.explanation = {'state': 'see_recommendations'}
            self.session.add(prediction)
        return event

    def refresh_evidence(self, recommendation_id):
        event = self.visible_event(recommendation_id)
        self.fill_evidence(event)
        self.session.commit()
        self.session.refresh(event)
        return self.event_response(event)

    def dashboard(self):
        if self.user.is_global_admin:
            missions = self.session.exec(select(Mission)).all()
        else:
            missions = self.session.exec(select(Mission).join(MissionMember, MissionMember.mission_id == Mission.id).where(MissionMember.user_id == self.user.id)).all()
        mission_rows, astronauts, levels, kinds, domains = [], [], Counter(), Counter(), Counter()
        for mission in missions:
            run = self.latest_run('mission', mission.id)
            predictions = self.session.exec(select(RiskPrediction).where(RiskPrediction.run_id == run.id)).all() if run else []
            signals = [p for p in predictions if p.prediction_kind != 'insufficient_data']
            mission_rows.append({'mission_id': mission.id, 'name': mission.name, 'status': mission.status, 'analyzed_at': run.as_of if run else None,
                                 'signals': len(signals), 'highest_level': max((p.risk_level for p in signals), key=lambda level: ['none', 'low', 'moderate', 'high'].index(level) if level in ('none', 'low', 'moderate', 'high') else -1, default=None),
                                 'risk_types': sorted({p.risk_type for p in signals})})
            for p in signals:
                levels[p.risk_level] += 1
                kinds[p.prediction_kind] += 1
                domains[p.domain] += 1
            members = self.session.exec(select(MissionMember).where(MissionMember.mission_id == mission.id, MissionMember.role == 'astronaut')).all()
            for member in members:
                try:
                    visible = self.astronaut_domains(member.user_id, mission.id)
                except HTTPException:
                    continue
                astronaut_run = self.latest_run('astronaut', member.user_id, mission.id)
                rows = self.session.exec(select(RiskPrediction).where(RiskPrediction.run_id == astronaut_run.id)).all() if astronaut_run else []
                rows = [p for p in rows if p.domain in visible]
                for p in rows:
                    if p.prediction_kind != 'insufficient_data':
                        levels[p.risk_level] += 1
                        kinds[p.prediction_kind] += 1
                        domains[p.domain] += 1
                user = self.session.get(User, member.user_id)
                astronauts.append({'astronaut_id': member.user_id, 'name': user.name if user else f'User #{member.user_id}', 'mission_id': mission.id, 'mission_name': mission.name,
                                   'analyzed_at': astronaut_run.as_of if astronaut_run else None,
                                   'signals': sum(1 for p in rows if p.prediction_kind != 'insufficient_data'),
                                   'insufficient': sum(1 for p in rows if p.prediction_kind == 'insufficient_data'),
                                   'risk_types': sorted({p.risk_type for p in rows if p.prediction_kind != 'insufficient_data'})})
        pending = [event for event in self.session.exec(select(RecommendationEvent).where(RecommendationEvent.status == 'pending').order_by(RecommendationEvent.rank_score.desc()).limit(300)).all() if self.can_view_event(event)]
        recent_runs = self.session.exec(select(PredictionRun).where(PredictionRun.mission_id.in_([m.id for m in missions])).order_by(PredictionRun.as_of.desc()).limit(200)).all() if missions else []
        history = Counter(aware(run.as_of).date().isoformat() for run in recent_runs if run.status == 'completed')
        return {'monitored_astronauts': len([row for row in astronauts if row['analyzed_at']]), 'visible_astronauts': len(astronauts),
                'monitored_missions': len([row for row in mission_rows if row['analyzed_at']]), 'missions': mission_rows, 'astronauts': astronauts,
                'risk_levels': dict(levels), 'prediction_kinds': dict(kinds), 'domains': dict(domains),
                'pending_recommendations': len(pending), 'top_recommendations': [self.event_response(event) for event in pending[:10]],
                'run_history': [{'date': day, 'runs': count} for day, count in sorted(history.items())],
                'failed_runs': sum(1 for run in recent_runs if run.status == 'failed'), 'notice': self.notice()}

    def models(self):
        rows = self.session.exec(select(PredictionModel).order_by(PredictionModel.name, PredictionModel.created_at.desc())).all()
        return [self.model_response(row) for row in rows]

    def model_response(self, model):
        values = model.model_dump(exclude={'artifact'})
        values['metadata'] = values.pop('model_metadata')
        return values

    def model_metrics(self, model_id):
        model = self.session.get(PredictionModel, model_id)
        if model is None:
            raise HTTPException(404, 'Model not found')
        return {'id': model.id, 'name': model.name, 'version': model.version, 'status': model.status, 'predicted_outcome': model.predicted_outcome,
                'horizon_hours': model.horizon_hours, 'validation_metrics': model.validation_metrics, 'trained_at': model.trained_at,
                'notice': 'Metrics come from a temporal hold-out of historical system data. Synthetic data is never clinical validation.'}

    def transition_model(self, model_id, target):
        self.require_global_admin()
        model = self.session.exec(select(PredictionModel).where(PredictionModel.id == model_id).with_for_update()).first()
        if model is None:
            raise HTTPException(404, 'Model not found')
        allowed = {'approved': {'candidate'}, 'active': {'approved', 'retired'}, 'retired': {'active', 'approved', 'candidate'}}
        if model.status not in allowed[target]:
            raise HTTPException(409, f'A {model.status} model cannot become {target}')
        if target in ('approved', 'active') and model.kind == 'supervised' and not (model.validation_metrics or {}).get('passed'):
            raise HTTPException(409, 'Only models that passed validation can be approved or activated')
        now = utc_now()
        if target == 'active':
            for current in self.session.exec(select(PredictionModel).where(PredictionModel.name == model.name, PredictionModel.status == 'active', PredictionModel.id != model.id)).all():
                current.status = 'retired'
                self.session.add(current)
            self.session.flush()
            model.activated_at = now
        if target == 'approved':
            model.approved_by_user_id = self.user.id
        model.status = target
        self.session.add(model)
        self.audit('prediction_models', model.id, f'model_{target}')
        self.session.commit()
        self.session.refresh(model)
        return self.model_response(model)
