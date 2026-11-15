# Health monitoring

An astronaut opens the monitoring dashboard as the home page. The astronaut profile is also recognized through the `astronaut` membership of earlier accounts. Physicians reach the dashboard from the menu and choose the mission and the authorized astronaut. The interface uses the existing components and blue palette, native SVG and Recharts.

Monitoring records are independent of exam results. Astronauts can add their own measurements, but still cannot change pre-mission exams. Monitoring observations are preserved: there are no edit or delete endpoints.

## Data and permissions

Each observation contains the astronaut, an optional mission, the indicator, values, collection time in UTC, recording time in UTC, source, responsible person, an optional note and the pre-mission reference flag. Blood pressure uses systolic and diastolic on the same row. Sleep uses whole minutes; the form and display use hours and minutes. Sleep session start and end are preserved and the duration is derived, without accepting a contradictory duration.

The backend validates format, scale domains, incompatible fields, dates with a time zone, future collection times and required pairs. These limits validate the data; they do not classify clinical risk.

Astronauts read and record only their own data. A physician with the `flight_surgeon` membership can view and record data of another astronaut in the same mission, always with an explicit `mission_id`. A mission administrator does not get clinical access for being an administrator. AVPU and pre-mission references require another authorized flight surgeon. Physicians who are also astronauts cannot record AVPU for themselves.

The API recognizes `self_report`, `manual_measurement` and `device`. There is no device source in the repository; creation with `device` is rejected until an integration exists. The interface allows self-reports and manual measurements.

## Endpoints

All use the `/v1` prefix.

| Method | Path | Use |
| --- | --- | --- |
| GET | `/health/context` | Own eligibility and astronauts followed in authorized missions |
| POST | `/health/astronauts/{user_id}/observations` | Add a validated observation |
| GET | `/health/astronauts/{user_id}/summary` | The 11 indicators, current and previous reading, reference, changes and permissions |
| GET | `/health/astronauts/{user_id}/history` | Paginated history per indicator and period |

`user_id` identifies `users.id`, not `mission_members.id`. The history requires `indicator` and accepts `mission_id`, `start`, `end`, `page` and `per_page` (maximum 100). Dates must include a time zone. Without a period, it returns the last 30 days. The interface reads every page and offers 24 hours, 7 days and 30 days. Without a mission, astronauts see their own set of observations; physician queries require a mission and do not include observations outside it.

Example body for heart rate:

```json
{
  "indicator": "heart_rate",
  "value": 72,
  "collected_at": "2026-11-11T12:00:00Z",
  "source": "manual_measurement",
  "mission_id": null,
  "note": null
}
```

Indicators: `heart_rate`, `blood_pressure`, `respiratory_rate`, `oxygen_saturation`, `body_temperature`, `consciousness`, `sleep_duration`, `sleep_quality`, `fatigue`, `mood`, `attention`.

For blood pressure, send `systolic` and `diastolic` without `value`. For AVPU, send `category` with `alert`, `voice`, `pain` or `unresponsive`. For attention, `better`, `usual` or `worse`. For sleep, send `value` in minutes or the `sleep_started_at`/`sleep_ended_at` pair. The AVPU source must be `manual_measurement`.

## References and trends

Existing pre-mission exams have a text clinical summary; they do not offer structured measurements that can be compared safely. That text is not extracted automatically. An authorized flight surgeon can record an observation with `is_preflight_reference=true`, linked to the mission and collected before the actual start, or before the planned launch while there is no actual start.

The summary uses the most recent reference of the same indicator and mission, earlier than or equal to the collection of the current reading. Numeric changes are absolute differences, keeping both blood pressure components. AVPU and attention offer sequences, without converting categories into scores. Missing values are returned as `null` or empty lists and shown as “No data”.

History and summary use `collected_at`, then `recorded_at` and ID as tie-breakers. A backdated record does not replace a more recent collection. Trends describe increase, decrease, stability or changes in different directions for the two blood pressure values, without diagnosing or suggesting clinical limits.

Charts keep every point, without averages or interpolation. Intervals without observations get null points in 1-hour, 6-hour or 1-day windows, depending on the period. The window length is an explicit display rule and does not assume a clinical collection frequency. The table keeps the values and dates of each observation. Lines use `connectNulls=false`, as in the [Recharts API](https://recharts.github.io/en-US/api/Line/).

## Run

In an installation with an intact migration history:

```sh
cd back
docker compose up --build -d
docker compose exec -T api alembic upgrade head
cd ../front
npm install
npm run dev
```

Vite forwards `/api` to the API on port 8000. Open the port Vite reports (5173, or the next available one).

The original database on the development machine still has the missing revision `7efe7ee6f54f`. It was not changed. The instance used for this implementation was `nasa-front-validation-api`, on port 8000, with the separate database `nasa_front_validation_20261111`. The health migration was also verified in the separate database `nasa_health_migration_20261111`, with upgrade, downgrade and a new upgrade, preserving the earlier user.

## Verification

Backend, in a separate, migrated development database:

```sh
cd back
docker compose exec -T api pip install pytest
docker compose exec -T -e PGDATABASE=nasa_front_validation_20261111 api alembic upgrade head
docker compose exec -T -e PGDATABASE=nasa_front_validation_20261111 api alembic check
docker compose exec -T -e PGDATABASE=nasa_front_validation_20261111 -e PREFLIGHT_POSTGRES_TESTS=1 api python -m pytest -q tests/test_health_postgres.py tests/test_preflight_postgres.py tests/test_auth.py tests/test_user_profiles.py
```

Frontend:

```sh
cd front
npm test
npm run build
HEALTH_TEST_URL=http://127.0.0.1:5174 npm run test:health:e2e
```

The browser test requires the backend and Vite to be running. It creates fictional accounts and a mission in the local API database. Use a separate database. Screenshots are written to `/tmp/nasa-health-e2e` or to `HEALTH_TEST_ARTIFACTS`. To use an installed Chrome, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`.

## Files of this implementation

Backend:

- `back/app/models/health.py`
- `back/app/schemas/health.py`
- `back/app/services/health_service.py`
- `back/app/routers/health.py`
- `back/app/main.py`
- `back/alembic/env.py`
- `back/alembic/versions/f718293a4b5c_add_health_observations.py`
- `back/tests/test_health_postgres.py`
- `back/README.md`

Frontend:

- `front/src/HealthDashboard.jsx`
- `front/src/health-indicators.js`
- `front/src/health.css`
- `front/src/main.jsx`
- `front/tests/health.test.js`
- `front/scripts/verify-health.mjs`
- `front/package.json`
- `front/package-lock.json`
- `front/README.md`

Documentation: `HEALTH_MONITORING.md`.

## Structures still missing

There are no connected devices, no structured values in pre-mission results and no configured, validated clinical rules. These gaps stay explicit: sensors are not simulated, references are not extracted from text and clinical alerts are not issued from them. Holding both the astronaut and physician roles in the same mission does not exist yet in the pre-mission module; monitoring recognizes the account's dual profile but still requires another assessor for AVPU.

## Verification result of this implementation

- 89 backend tests passed, with 6 optional knowledge tests disabled.
- Frontend tests and the production build passed.
- A real browser test passed on desktop and at 390 px: initial astronaut access, 11 hotspots and cards, keyboard selection, recording of the 11 indicators, two blood pressure series, sleep in hours and minutes and by session, backdated collection, the 24-hour filter, the categorical timeline, AVPU assessment by an authorized physician and blocking between astronauts.
- No JavaScript errors during the verified flow.
- Upgrade, downgrade and a new upgrade of the migration preserved the earlier user in the isolated database.
- `alembic check` found no differences between the migrated schema and the models.

Local screenshots: `/tmp/nasa-health-e2e/desktop.png` and `/tmp/nasa-health-e2e/mobile.png`.

## Demonstration with fictional data

The command below creates demonstration accounts and 468 observations for the 11 indicators, including pre-mission references, a 30-day history and gaps. Running it again does not duplicate observations. The script only accepts databases with `validation`, `demo` or `test` in the name.

```sh
cd back
docker compose exec -T -e PGDATABASE=nasa_front_validation_20261111 api python -m scripts.seed_health_demo
```

Select the demonstration astronaut (`astronauta.demo@example.com`) or the demonstration physician (`medica.demo@example.com`) with the **Profile** and **User** selectors, then choose the demonstration mission and the astronaut. All generated records are labeled as fictional. Their names and notes are kept as originally created so that repeated runs do not duplicate them. The script is in `back/scripts/seed_health_demo.py`.
