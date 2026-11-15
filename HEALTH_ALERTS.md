# Health alerts

The evaluation is deterministic and does not use AI, diagnosis, prescription or medication recommendations. The ranges are a simulation profile, not universal clinical rules.

## Configuration

The file `back/app/config/health_alert_profiles.json` contains the `simulation-v1` and `simulation-v2` profiles, the ranges, the day/night sequences and the measurement freshness windows. To change simulation ranges, create a new version in the file and update the profiles accepted in the schema. Do not replace the definition of a version already in use. Each evaluated measurement and each alert keep a copy of the profile used; events keep the version.

In health monitoring, select a mission and use **Configure alert profile**. Physicians assigned as `flight_surgeon` or `mission_admin` can configure:

- The mission IANA time zone, such as `America/Bahia`.
- The emergency channel.
- SpO₂ limits approved by the medical team.
- Optional high glucose limits per context: fasting, after a meal or unknown context.
- The record of the medical approval.

Each change creates a new revision. Concurrent changes require reloading the configuration through the expected revision. The current default is `simulation-v2`, in UTC, with an urgent alert for glucose ≥300 mg/dL in the fasting, after-meal and unknown contexts. These limits are explicitly configured for the simulation. The `simulation-v1` profile is kept without a default high glucose rule; mission configurations already approved are not replaced. Without a selected mission, the default profile in UTC is used.

## Measurements

The form shows only the fields relevant to the indicator. Glucose asks for the value, meal context and reading quality; supplemental oxygen appears only for saturation and respiratory rate. Sleep and subjective scales do not ask for sensor quality. The existing measurements POST accepts the following additional fields:

| Field | Values |
| --- | --- |
| `activity` | `rest`, `exercise`, `unknown` |
| `signal_quality` | `good`, `poor`, `unknown` |
| `supplemental_oxygen` | `true`, `false`, `null` |
| `glucose_context` | `fasting`, `after_meal`, `unknown` |
| `symptoms_status` | `present`, `absent`, `unknown` |
| `symptoms` | `chest_pain`, `shortness_of_breath`, `sudden_weakness`, `visual_changes`, `speech_difficulty` |
| `acute_confusion` | `true`, `false`, `null`; only for attention/consciousness |
| `unit` | The indicator unit or a supported alternative |
| `client_request_id` | Retry UUID |

The alternative units are °F for temperature, mmol/L for glucose, kPa for blood pressure, `fraction` for SpO₂ and `h` for sleep duration. Normalized values are used in the rules and the history; `original_values` keeps the values and unit that were sent. The canonical respiratory rate unit is `breaths/min`; the earlier `respirações/min` is still accepted and is converted by migration `4a2b3c4d5e61`.

When no symptoms are recorded, symptoms remain unknown. Structured present symptoms raise very high blood pressure to critical. Free text is not interpreted as acute confusion or as the presence or absence of symptoms.

Resting heart rate and respiratory rate ranges are only applied with `activity=rest`. With unknown activity, critical resting ranges create an urgent operational alert for immediate verification, without classifying the reading as confirmed at rest. Exercise keeps its context; an extreme reading with a poor signal also requires immediate verification. SpO₂, temperature, blood pressure, low glucose and consciousness use the configured rules regardless of activity, keeping the context.

A reading with a poor signal keeps insufficient quality. If it reaches an alert range, the alert is raised immediately with an explicit verification requirement. No poor-signal reading closes or lowers an open alert.

The summary distinguishes `no_measurement`, `stale`, `insufficient_quality`, `evaluated` and `not_evaluated`. Measurements from before the migration stay not evaluated; alerts are not generated retroactively. An old reading is marked as outdated and keeps its context and quality in the history.

## Trends

The latest valid record per day or night is used, with ties broken by recording time and ID. Records with insufficient quality do not enter trends. The time zone is the mission's. For sleep sessions, the night is identified by the local date of the session end; without a session, by the local collection date. Several readings in the same day or night do not complete a sequence. A day or night without a valid record breaks the sequence. A late recording can complete the sequence, but a reading outside it does not reopen a trend that was already resolved.

## Lifecycle and access

The states are `open`, `acknowledged` and `resolved`. Acknowledging records that the alert was seen. An escalation reopens the alert and keeps the earlier acknowledgment in the history. Attention and urgent alerts close automatically after a new valid, recent reading outside the rule range. An old reading, a poor signal or a reading without the necessary context does not close the alert. In trends, a single gap does not mean normalization. Critical alerts still require explicit resolution by the authorized flight surgeon. When the current reading is already outside the range, the interface distinguishes the earlier critical event from the pending medical review. A new occurrence after resolution creates another alert and keeps the earlier one.

There is a single active alert per rule and crew member, regardless of the source mission. Alerts are part of the crew member's medical record, like allergies: the crew member can view and acknowledge them; the flight surgeon assigned to the given mission can view, acknowledge and resolve them. Other crew members, unassigned physicians and administrators without a clinical role cannot access the alerts. The list and history show the crew member's source measurements, including those recorded in another mission.

The server serializes writes and actions per crew member with a row lock. Unique constraints protect the retry key, the measurement content and the crew member/active rule combination. A key reused with different content returns 409. Forms keep the UUID during resubmissions.

## Routes

All routes use the `/v1/health` prefix and require authentication.

| Route | Method |
| --- | --- |
| `/astronauts/{astronaut_id}/observations` | Existing POST, now evaluates alerts in the same transaction |
| `/astronauts/{astronaut_id}/summary` | Existing GET, now returns the evaluation state and context |
| `/astronauts/{astronaut_id}/history` | Existing GET, now includes the original unit and context |
| `/astronauts/{astronaut_id}/alerts` | GET, `status=active/all/open/acknowledged/resolved`, `indicator`, `page`, `per_page` |
| `/astronauts/{astronaut_id}/alerts/{alert_id}` | GET |
| `/astronauts/{astronaut_id}/alerts/{alert_id}/history` | Paginated GET with events and source measurements |
| `/astronauts/{astronaut_id}/alerts/{alert_id}/acknowledge` | POST |
| `/astronauts/{astronaut_id}/alerts/{alert_id}/resolve` | POST with `{"note":"Assessment recorded"}` |
| `/missions/{mission_id}/alert-settings` | GET, PUT |

Provide `mission_id` in the flight surgeon's queries and actions. Crew members can also view their own alerts without a mission.

## Screen

Health monitoring shows active alerts inside the card of each indicator, most severe first in each card. The card is highlighted with text, an icon and color. The history opened from the card is filtered by the indicator. There are actions to record a new measurement or symptoms, open the indicator history, acknowledge, view the alert events and record an authorized resolution. Card columns are independent; expanding a card does not stretch the neighboring card. The alert and event histories have a page size selector, the total number of records and Previous/Next navigation. Critical alerts show the emergency protocol and the current mission channel. When the channel is missing, that is stated explicitly. The historical snapshot of the original channel is preserved.

## Migration and checks

From `back/`:

```sh
docker compose exec -T api alembic upgrade head
```

The revision is `d15c6e7f8091`. It adds context to measurements and the `health_alert_settings`, `health_alerts`, `health_alert_observations` and `health_alert_events` tables. Reverting is blocked when alerts exist, to preserve history.

With pytest available in the backend environment:

```sh
python -m pytest -q
python -m scripts.verify_health_alerts
```

The second command creates a temporary PostgreSQL database, applies all migrations, runs the suite with the PostgreSQL and concurrency tests enabled and removes the database at the end. It requires permission to create and drop that isolated database. The concurrency test sends four simultaneous resubmissions and two simultaneous measurements with an escalation.

From `front/`:

```sh
npm test
npm run build
```

## High glucose in the simulation profile

Version `simulation-v2` adds an urgent operational limit of 300 mg/dL for high glucose, with confirmation of the reading. The profile does not diagnose ketoacidosis or determine treatment. The reference consulted was the CDC guidance on glucose persistently ≥300 mg/dL, which must not be read as a universal rule for a single reading: https://www.cdc.gov/diabetes/about/diabetic-ketoacidosis.html . Choosing a single value as the initial trigger is a product decision for the prototype and requires specific clinical configuration for use outside the simulation.

An explicit re-evaluation can keep the earlier profile and state in `evaluation_profile.previous_evaluation`, keeping the measurement ID, time and original value. Changing the default profile does not automatically reprocess all old records.

Alert reasons and notes are stored with the alert when it is created. Alerts created before the English translation keep their original text.
