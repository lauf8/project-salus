import argparse
import json
import logging
import os
import time
from datetime import timedelta

from fastapi import HTTPException
from sqlmodel import Session, select

from app.database import engine
from app.models.predictive import PredictionModel, PredictionRun, RecommendationEvent, RiskPrediction
from app.models.preflight import Mission, MissionMember, utc_now
from app.services.predictive.data_collection import AstronautDataCollector
from app.services.predictive.features import aware
from app.services.predictive.recommendations import sync_catalog
from app.services.predictive.training import OUTCOMES, live_performance
from app.services.predictive_service import PredictiveService


def analyze(label, operation):
    try:
        with Session(engine) as session:
            run = operation(PredictiveService(session, None))
            return {'subject': label, 'run_id': run.id, 'status': run.status, 'trigger': run.trigger}
    except HTTPException as exc:
        return {'subject': label, 'status': 'failed', 'error': exc.detail}
    except Exception:
        logging.exception('Predictive analysis failed for %s', label)
        return {'subject': label, 'status': 'failed'}


def active_missions():
    with Session(engine) as session:
        missions = session.exec(select(Mission).where(Mission.started_at.is_not(None), Mission.ended_at.is_(None))).all()
        return [(mission.id, mission.spacecraft_id, [member.user_id for member in session.exec(select(MissionMember).where(MissionMember.mission_id == mission.id, MissionMember.role == 'astronaut')).all()]) for mission in missions]


def fill_evidence(limit=20):
    filled = 0
    with Session(engine) as session:
        events = session.exec(select(RecommendationEvent).where(RecommendationEvent.status.in_(['pending', 'accepted'])).order_by(RecommendationEvent.id)).all()
        for event in [row for row in events if row.explanation.get('state') == 'pending'][:limit]:
            try:
                PredictiveService(session, None).fill_evidence(event)
                session.commit()
                filled += 1
            except Exception:
                session.rollback()
                logging.exception('Evidence retrieval failed for recommendation %s', event.id)
    return filled


def monitor_models():
    results = []
    with Session(engine) as session:
        for model in session.exec(select(PredictionModel).where(PredictionModel.status == 'active', PredictionModel.kind == 'supervised')).all():
            outcome = OUTCOMES.get(model.predicted_outcome)
            if outcome is None:
                continue
            rows = session.exec(select(RiskPrediction, PredictionRun).join(PredictionRun, PredictionRun.id == RiskPrediction.run_id).where(
                RiskPrediction.model_id == model.id, RiskPrediction.calibrated_probability.is_not(None))).all()
            matured = [(prediction, run) for prediction, run in rows if aware(run.as_of) + timedelta(hours=outcome.horizon_hours) <= utc_now()]
            collector = AstronautDataCollector(session)
            records = {}
            pairs = []
            for prediction, run in matured:
                if run.subject_id not in records:
                    records[run.subject_id], _ = collector.collect(run.subject_id, run.mission_id, utc_now())
                pairs.append((prediction, run, records[run.subject_id]))
            report = live_performance(model, pairs, outcome)
            model.model_metadata = {**model.model_metadata, 'monitoring': report}
            session.add(model)
            results.append({'model_id': model.id, **{key: report.get(key) for key in ('state', 'evaluated')}})
        session.commit()
    return results


def synchronize():
    with Session(engine) as session:
        sync_catalog(session)
        session.commit()
    results = []
    for mission_id, spacecraft_id, astronauts in active_missions():
        for astronaut_id in astronauts:
            results.append(analyze(f'astronaut:{astronaut_id}', lambda service, a=astronaut_id, m=mission_id: service.analyze_astronaut(a, m, trigger='scheduled')))
        results.append(analyze(f'mission:{mission_id}', lambda service, m=mission_id: service.analyze_mission(m, trigger='scheduled')))
        if spacecraft_id:
            results.append(analyze(f'spacecraft:{spacecraft_id}', lambda service, s=spacecraft_id: service.analyze_spacecraft(s, trigger='scheduled')))
    return {'analyses': results, 'evidence_filled': fill_evidence(), 'model_monitoring': monitor_models()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    interval = max(30, int(os.getenv('PREDICTION_WORKER_INTERVAL_SECONDS', '300')))
    while True:
        try:
            print(json.dumps(synchronize(), default=str), flush=True)
        except Exception:
            logging.exception('Predictive synchronization unavailable; will retry')
        if not args.watch:
            break
        time.sleep(interval)


if __name__ == '__main__':
    main()
