# Internal clinical notifications

The Notifications area and the bell in the header are shown to physician accounts. The list queries the backend every 30 seconds while the page is visible. The bell also refreshes when you return to the window and after read actions. There is no webhook, email, push, sound or external integration.

## When a notification is created

Only an alert with `critical` severity, raised by a recent reading that is still the latest valid reading of that indicator, can create a notification. Readings with `poor` quality, outdated readings, or readings already replaced by a more recent valid measurement do not create new notices. Attention and urgent alerts, including the urgent high glucose alert of the simulation profile, do not create notifications. The criterion uses the existing simulation rules; it does not establish a diagnosis.

An escalation to critical creates a notification. If the first critical reading has a poor signal, a later valid critical reading can create the first notice. Resubmissions, repeated critical measurements and acknowledging the same alert do not create duplicate notices. After resolution, a new occurrence creates another alert and can create another notification.

Notifications are stored in the same transaction as the measurement and the alert, with a unique key per physician, mission and alert. The notification data keeps the reason and the measurement that triggered the notice. The current alert state is read when the notification is displayed.

## Recipients and access

The recipient must have `is_physician=true` and be assigned to the mission as `flight_surgeon`, and must be a different user from the crew member being assessed. Only the recipient can view their notifications or mark them as read. The clinical membership and the crew member membership are checked again on every query; removing or changing the flight surgeon role revokes access to that mission's notifications.

The mission given in the measurement is used for routing. If the measurement has no mission, the only open mission in which the crew member has the `astronaut` role is used. If there are zero or several, the system does not pick a team arbitrarily; the measurement context records that the mission must be provided. Closed missions do not receive new notices. If there is no eligible flight surgeon, that is also recorded in the measurement context.

Marking a notification as read only records the reading. It does not acknowledge or resolve the alert. The Pending tab and the bell counter show unread notices whose alert has not been resolved. The All tab keeps the history, including notifications of resolved alerts. Opening the medical record marks the notification as read and selects the mission, crew member and indicator in monitoring, keeping the existing access rules.

## Routes

All routes require a physician account and use the `/v1` prefix.

| Route | Method and behavior |
| --- | --- |
| `/notifications` | GET with `status=pending/all`, optional `mission_id`, `page` and `per_page` |
| `/notifications/summary` | GET with the unread and pending counts |
| `/notifications/{notification_id}/read` | POST to mark one of your notifications as read |
| `/notifications/read-all` | POST to mark all notifications visible to the recipient as read |

## Installation and verification

From `back/`:

```sh
docker compose exec -T api alembic upgrade head
docker compose exec -T api python -m scripts.sync_health_notifications
```

Revision `e26d7f8091a2` creates `health_notifications`. The synchronization checks existing critical alerts with the same recency, quality and routing criteria; it does not create notices for superseded events. It can be repeated without duplicates. Evaluating new measurements already creates notifications automatically, without depending on this command.

With pytest installed:

```sh
python -m pytest -q tests/test_health_notifications.py
python -m scripts.verify_health_alerts
```

The PostgreSQL verifier creates and removes an isolated database and tests concurrent writes, including the creation of a single notification on a critical escalation.
