Mission spacecraft reservations
===============================

Apply migrations with `alembic upgrade head` before running the updated application. The migration retains existing missions, derives mission status from their existing dates, and leaves their spacecraft reference null.

`POST /v1/missions` accepts an optional nullable `spacecraft_id`. Supplying an available spacecraft reserves it in the same transaction that creates the mission and its administrator membership. Unavailable spacecraft produce HTTP 409; unknown IDs produce HTTP 404.

`PATCH /v1/missions/{id}` accepts `status` (`planned`, `in_progress`, `completed`) and an optional nullable `spacecraft_id`. Completion retains the historical link and releases the reservation once. Reopening reserves the spacecraft again. Swapping or clearing a spacecraft on an open mission releases its previous reservation. Deletion releases an open mission's reservation after the existing deletion checks pass. Spacecraft with historical mission references cannot be deleted.

Existing date updates also update mission status. Setting an end date completes the mission; clearing an existing end date reopens it. An explicit status takes precedence. New missions without dates indicating progress default to `planned`; new spacecraft default to `available`.

The spacecraft status is managed by mission reservations and is read-only in the spacecraft API. A conditional database update prevents concurrent reservations, and a partial unique index provides an additional guarantee that a spacecraft has at most one open mission.

Validation
----------

Run `pytest tests/test_mission_spacecraft.py` for service and HTTP checks. Run `MISSION_POSTGRES_TESTS=1 pytest tests/test_mission_spacecraft_migration.py` against a dedicated PostgreSQL validation database to check migration preservation and downgrade in an isolated transactional schema.

In the frontend, run `npm test`, `npm run typecheck`, `npm run build`, and `npm run test:missions:e2e`. The browser test uses mocked API responses to check required spacecraft selection, unavailable spacecraft filtering, conflict recovery, preserved form fields, and empty availability.

Crew planning
-------------

Missions expose nullable `crew_size`, the planned number of astronauts. Existing missions are backfilled with the number of astronaut memberships, or null when no astronauts are assigned. Mission administrators and flight surgeons are ground roles and do not consume flight seats.

Mission creation accepts `astronaut_ids` and creates their memberships atomically with the mission and reservation. The IDs must be unique and refer to users with an astronaut profile. The creator retains the administrator membership and cannot also be selected as an astronaut in that mission.

The assigned astronaut count cannot exceed `crew_size` when specified, and neither the planned nor assigned crew can exceed the spacecraft's `maximum_crew_capacity` when specified. These checks also apply when changing a membership role, changing the spacecraft, reopening a mission, or reducing the spacecraft capacity for an open mission. Unknown legacy capacities remain supported.

`GET /v1/users/?search=Alice&is_astronaut=true` searches names without case sensitivity and supports the existing pagination parameters. Creation and the mission Crew tab use this endpoint to add astronauts individually.
