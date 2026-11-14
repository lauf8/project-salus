# Mental health

The mission page includes a Mental health tab for astronauts and assigned psychologists. The interface follows the application's existing English language.

Register a psychologist profile, then have a mission administrator add that user to the crew with the `psychologist` role. The profile alone does not grant access. A psychologist assigned to the mission may read its astronauts' journals and record conversations. Removing the psychologist's mission membership revokes access while retaining session authorship. Astronaut memberships with journal, request, or session history cannot be deleted or repurposed.

Daily check-ins use the timezone in `health_alert_settings`, with UTC as the project fallback. Dates are explicit, permit retrospective entries, and cannot be in the future. `PUT` replaces a daily record; omitted optional fields become null. A unique constraint and a membership row lock enforce one record per astronaut membership and date. A missing day remains a gap. No clinical score, diagnosis, or AI processing is attached to this module.

Mission weeks are consecutive seven-day periods anchored to the actual mission start, falling back to planned launch, in the mission timezone. Weekly coverage uses the recorded review period. Multiple sessions can cover the same week. The overview accepts `start` and `end` with a maximum of 367 days, and returns explicit missing days, weekly coverage, and separate existing sleep measurements without their notes.

## API

All paths start with `/v1/missions/{mission_id}/mental-health` and require authentication.

- `GET /astronauts`: psychologist roster, pending requests, weekly coverage.
- `GET /astronauts/{member_id}?start=YYYY-MM-DD&end=YYYY-MM-DD`: authorized overview.
- `PUT /astronauts/{member_id}/check-ins/{check_in_date}`: astronaut's own daily check-in.
- `POST /astronauts/{member_id}/requests`: astronaut's conversation request; retries return the pending request.
- `POST /astronauts/{member_id}/sessions`: assigned psychologist's follow-up.
- `PUT /astronauts/{member_id}/sessions/{record_id}`: responsible psychologist's correction.

Sessions can fulfill one pending request from the same astronaut membership and mission. Linking and fulfillment are committed atomically. A session's request link is immutable after creation. After fulfillment, the astronaut can submit another request.

`session_summary` and `private_notes` never appear in astronaut responses. Agreed actions and return dates are shared only through the independent `share_agreed_actions` and `share_next_follow_up` switches, both false by default. Text is excluded from the roster, general mission responses, audit events, and validation error responses. The module does not emit journal or session text to logs or telemetry. Audit events contain actor, resource, action, mission, and timestamp only. Read access is audited as well as writes.

## Migration and validation

Apply Alembic revision `f9de4567a819` through the existing startup migration process or `alembic upgrade head`. It adds the psychologist profile, mission role, and four module tables. Downgrade requires removing psychologist mission memberships first because the earlier role constraint cannot represent them.

Backend checks: `pytest -q`. Set `MENTAL_HEALTH_POSTGRES_TESTS=1` to include the full migration chain, downgrade/upgrade, and concurrent daily/request submission tests. These PostgreSQL checks create isolated schemas and remove them afterward.

Frontend checks: `npm test`, `npm run typecheck`, `npm run build`, and `npm run test:mental-health:e2e`. The browser test uses mocked API responses to verify both workflows, explicit sharing, gaps, and preservation of entered text after failed saves. Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` if Chrome is installed at a different path.
