# Project Salus

- Write code, identifiers, and technical names in English.
- Do not add code comments. Use clear names and readable structures.
- Communicate progress and results directly, without flattery.
- Follow existing backend and frontend conventions.
- Reuse models, services, components, and permissions when they support the flow.
- Preserve compatibility with existing records. Use migrations for schema changes.
- Preserve the existing interface language and UI patterns.
- Keep secrets and environment-specific settings out of versioned code.
- Keep feature-specific design, configuration, limitations, and reproduction steps in feature documentation.
- Attach an original local copy of every source document used by the project. For NASA references, store it under `back/data/nasa_references/` and record the official URL, verified revision/date, SHA-256, and page count in the source catalog.

## Confirmed commands

Backend commands run from `back/`:

- `docker compose up -d`: start PostgreSQL and API; startup applies migrations and imports public knowledge.
- `docker compose exec -T api alembic upgrade head`: apply migrations.
- `docker compose exec -T api alembic heads`: inspect migration heads.
- `docker compose exec -T api python -m pytest -q`: run backend tests when pytest is installed in the execution environment.
- `docker compose exec -T api python -m scripts.sync_health_notifications`: synchronize clinical notifications.

Frontend commands run from `front/`:

- `npm run dev`: start Vite with the API proxy.
- `npm run build`: create the production build.
- `npm test`: run Node tests.
- `npm run typecheck`: run TypeScript checks.
- `npm run test:nutrition:e2e`: run the nutrition browser flow.
- `npm run test:missions:e2e`: run the mission browser flow.
- `npm run test:risks:e2e`: run the mission risks browser flow.

Use `git diff --check` to check whitespace. Inspect feature documentation for additional verification commands.

Backend test dependencies are listed in `back/requirements-dev.txt`. Mission-risk verification commands and environment flags are documented in `MISSION_RISKS.md`.
