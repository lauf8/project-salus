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
- `docker compose exec -T api python -m scripts.predictive_worker`: run one predictive analysis cycle.
- `docker compose exec -T api python -m scripts.train_prediction_models --dry-run`: evaluate candidate predictive models without registering them.

Frontend commands run from `front/`:

- `npm run dev`: start Vite with the API proxy.
- `npm run build`: create the production build.
- `npm test`: run Node tests.
- `npm run typecheck`: run TypeScript checks.
- `npm run test:nutrition:e2e`: run the nutrition browser flow.
- `npm run test:missions:e2e`: run the mission browser flow.
- `npm run test:risks:e2e`: run the mission risks browser flow.
- `npm run test:predictive:e2e`: run the Predictive Intelligence browser flow.

Use `git diff --check` to check whitespace. Inspect feature documentation for additional verification commands.

Backend test dependencies are listed in `back/requirements-dev.txt`. Mission-risk verification commands and environment flags are documented in `MISSION_RISKS.md`.

## Architecture conventions

- Backend: FastAPI routers in `back/app/routers/` mounted under `/v1`; SQLModel tables in `back/app/models/`; Pydantic schemas in `back/app/schemas/`; business rules in `back/app/services/`. Services receive `(session, user)`. Mission access goes through `PreflightService._access`; astronaut health access follows `HealthService.authorize`; mental health access follows `MentalHealthService.scope`.
- Identity: the public profile selector sends `X-Public-User` and `X-Public-Profile`; profile flags on `users` and roles in `mission_members` drive authorization. Global administrators do not get astronaut health data by default.
- Schema changes: one Alembic revision per change in `back/alembic/versions/`, keeping a single head. Register new model modules in `back/alembic/env.py`.
- Background work: long-running scripts in `back/scripts/` run as Compose services (`risk-worker`, `predictive-worker`). Do not train models or call slow external services inside HTTP requests unless an existing flow already does so.
- Ollama and RAG: reuse `app/services/mission_rag.py`. Send the minimum data needed, validate generated output against the retrieved evidence and keep deterministic fallbacks.
- Clinical safety: never lower, close or replace clinical alerts from statistical outputs. Show probabilities only for validated, calibrated models. Report insufficient data explicitly.
- Tests: pure logic in `back/tests/` without a database; PostgreSQL flows in isolated schemas gated by an environment flag (`MISSION_RISKS_POSTGRES_TESTS`, `PREDICTIVE_POSTGRES_TESTS`). Frontend helpers in plain `.js` modules tested with `node --test`; browser flows in `front/scripts/verify-*.mjs`.
- Predictive Intelligence design, limitations and verification are documented in `PREDICTIVE_INTELLIGENCE.md`.
