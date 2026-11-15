import argparse
import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.database import engine
from app.models.predictive import PredictionModel
from app.models.preflight import MissionMember
from app.services.predictive.config import rules_config
from app.services.predictive.data_collection import AstronautDataCollector
from app.services.predictive.training import OUTCOMES, train_outcome_model


def register(session, outcome, result):
    now = datetime.now(timezone.utc)
    metrics = {key: value for key, value in result.items() if key not in ('artifact', 'artifact_sha256')}
    model = PredictionModel(name=f'astronaut_{outcome.name}', kind='supervised', subject_type='astronaut', risk_type=outcome.name,
                            version=now.strftime('v%Y%m%d%H%M%S'), predicted_outcome=outcome.name, horizon_hours=outcome.horizon_hours,
                            status='candidate' if result['passed'] else 'rejected', validation_metrics=metrics,
                            model_metadata={'feature_set_version': rules_config()['feature_set_version'], 'rules_version': rules_config()['version'],
                                            'algorithm': result.get('selected'), 'training_source': 'historical system records'},
                            artifact=result.get('artifact'), artifact_sha256=result.get('artifact_sha256'), trained_at=now)
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


def main():
    parser = argparse.ArgumentParser(description='Train candidate predictive models from historical records. Models are never activated automatically.')
    parser.add_argument('--outcome', choices=sorted(OUTCOMES), default='elevated_fatigue_24h')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    outcome = OUTCOMES[args.outcome]
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        astronauts = sorted(set(session.exec(select(MissionMember.user_id).where(MissionMember.role == 'astronaut')).all()))
        collector = AstronautDataCollector(session)
        records = {astronaut_id: collector.collect(astronaut_id, None, now)[0] for astronaut_id in astronauts}
        result = train_outcome_model(records, rules_config(), outcome)
        summary = {key: result.get(key) for key in ('outcome', 'data', 'selected', 'passed', 'reasons', 'metrics', 'baselines')}
        if not args.dry_run and result.get('artifact'):
            model = register(session, outcome, result)
            summary.update({'model_id': model.id, 'version': model.version, 'status': model.status})
        print(json.dumps(summary, indent=2, default=str))


if __name__ == '__main__':
    main()
