import argparse
import json
import logging
import time
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.database import engine
from app.models.mission_risks import MissionRiskAlert, MissionRiskEvaluation, MissionRiskPlan
from app.models.preflight import Mission
from app.models.user import User
from app.services.mission_risk_service import MissionRiskService


def synchronize():
    with Session(engine) as session:
        ids = session.exec(select(Mission.id).join(MissionRiskPlan).where(Mission.ended_at.is_(None)).distinct()).all()
    results = []
    for mission_id in ids:
        try:
            with Session(engine) as session:
                plan = session.exec(select(MissionRiskPlan).where(MissionRiskPlan.mission_id == mission_id).order_by(MissionRiskPlan.id.desc())).first()
                actor = session.get(User, plan.author_user_id)
                if not actor or not actor.is_active:
                    continue
                service = MissionRiskService(session, actor)
                latest = session.exec(select(MissionRiskEvaluation).where(MissionRiskEvaluation.mission_id == mission_id, MissionRiskEvaluation.state != 'replay').order_by(MissionRiskEvaluation.id.desc())).first()
                if latest is None or latest.evaluated_at.date() < datetime.now(timezone.utc).date():
                    service.evaluate(mission_id)
                alerts = session.exec(select(MissionRiskAlert).where(MissionRiskAlert.mission_id == mission_id, MissionRiskAlert.status != 'resolved')).all()
                for alert in alerts:
                    if alert.guidance.get('state') == 'pending':
                        service.guidance(mission_id, alert.id)
                results.append({'mission_id': mission_id, 'state': 'evaluated'})
        except Exception:
            logging.exception('Mission risk synchronization failed for mission %s', mission_id)
            results.append({'mission_id': mission_id, 'state': 'failed'})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    while True:
        try:
            print(json.dumps(synchronize()), flush=True)
        except Exception:
            logging.exception('Mission risk synchronization unavailable; will retry')
        if not args.watch:
            break
        time.sleep(60)


if __name__ == '__main__':
    main()
