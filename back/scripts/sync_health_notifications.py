import json

from sqlmodel import Session, select

from app.database import engine
from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlert
from app.models.user import User
from app.services.notification_service import NotificationService


def main():
    with Session(engine) as session:
        alert_ids = session.exec(select(HealthAlert.id).where(HealthAlert.severity == 'critical', HealthAlert.status.in_(['open', 'acknowledged'])).order_by(HealthAlert.id)).all()
    created = 0
    for alert_id in alert_ids:
        with Session(engine) as session:
            alert = session.get(HealthAlert, alert_id)
            observation = session.get(HealthObservation, alert.trigger_observation_id)
            actor = session.get(User, observation.recorded_by_user_id)
            created += NotificationService(session, actor).notify_critical(alert, observation)
            session.commit()
    print(json.dumps({'critical_alerts_checked': len(alert_ids), 'notifications_created': created}))


if __name__ == '__main__':
    main()
