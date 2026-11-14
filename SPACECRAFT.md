# Spacecraft and module catalog

The catalog is independent of missions. No spacecraft-to-mission relationship or existing mission schema was added.

## Project conventions

The backend uses FastAPI, SQLModel, Alembic and PostgreSQL. Both tables use integer primary keys, matching the existing database. The application exposes the routes under `/v1/spacecraft` and uses the existing `data` / `pagination` response envelope.

All authenticated users can read the catalog. Writes reuse the existing catalog permission: a physician assigned as a mission administrator or flight surgeon. The UI uses the existing `health/context.can_manage_catalog` capability and the existing HTTP client.

The existing frontend is React 19 with Vite, rather than Next.js. The new screens and form logic are TypeScript, use the existing layout and modal styles, and keep the interface in English. Yes / No / Unknown correspond to `true` / `false` / `null`.

## Migration

From `NASA`:

```bash
docker compose exec -T api alembic upgrade head
```

The catalog revision is `a48f9012b3c4`, following `f37e8091a2b3`. The subsequent revision `b59a0123c4d5` adds nullable `maximum_crew_capacity` to spacecraft with a positive integer check. It creates `spacecraft` and `spacecraft_modules`, including the restricted foreign key, unique module code per spacecraft, positive year and volume checks, and PostgreSQL JSONB specifications. Both revisions have been applied to the development database.

## API behavior

- `GET /v1/spacecraft?search=...&page=1&per_page=20` searches name, model and manufacturer.
- `POST /v1/spacecraft` creates a spacecraft.
- `GET`, `PATCH`, `DELETE /v1/spacecraft/{spacecraft_id}` read, update and delete a spacecraft.
- `GET /v1/spacecraft/{spacecraft_id}/modules?search=...&page=1&per_page=20` searches module name and code within that spacecraft.
- `POST /v1/spacecraft/{spacecraft_id}/modules` creates a module with its parent taken from the path.
- `GET`, `PATCH`, `DELETE /v1/spacecraft/{spacecraft_id}/modules/{module_id}` always scope the module to its parent.

PATCH leaves omitted fields unchanged. Explicit null clears optional fields. Supplying `technical_specifications` replaces the complete specification, without merging nested objects. Null clears it. This behavior is also described in the OpenAPI schema.

Duplicate module codes within a spacecraft and deletion of a spacecraft with modules return 409. The same code is allowed in different spacecraft. A wrong module parent returns 404. Changing `spacecraft_id` in a PATCH is rejected. Database conflicts roll back the transaction.

Maximum crew capacity is the number of people the spacecraft supports. It is optional, accepts integers from 1 through 2147483647, and can be cleared with null. Years must be integers from 1 through 32767. Dimensions, mass and volume must be finite and greater than zero. Technical references must be HTTP or HTTPS URLs. Names, codes and material names are trimmed and cannot be blank. Specifications can be partial; every material requires a component and material name.

## Frontend

Select Spacecraft in the sidebar. Detail views use `#spacecraft/{id}` and `#spacecraft/{id}/modules/{module_id}`, so reload restores the selected record. Forms preserve typed values on errors and show field validation and code conflicts beside the corresponding field. Materials support adding and removing rows. Editing an unchanged specification omits it from PATCH; editing a specification sends all its current dimensions, mass, material metadata, insulation and shielding.

## Verification

From `front`:

```bash
npm test
npm run typecheck
npm run build
```

From `NASA`, with an isolated migrated PostgreSQL database:

```bash
docker compose exec -T -e PGDATABASE=nasa_spacecraft_test api alembic upgrade head
docker compose exec -T -e PGDATABASE=nasa_spacecraft_test -e PREFLIGHT_POSTGRES_TESTS=1 -e KNOWLEDGE_POSTGRES_TESTS=1 -e SPACECRAFT_POSTGRES_TESTS=1 api python -m pytest -q
docker compose exec -T -e PGDATABASE=nasa_spacecraft_test api alembic check
```

The database must exist before running those commands. Pytest is required in the validation environment. The existing unrelated health-alert concurrency test requires its own specially named database and is skipped by this command.

The browser verification requires a dedicated local API with the migration applied, the frontend dev server, and Playwright Chromium:

```bash
SPACECRAFT_TEST_URL=http://127.0.0.1:5176 SPACECRAFT_TEST_API_URL=http://127.0.0.1:8002 npm run test:spacecraft:e2e
```

The script creates fictional users and a mission only to obtain the existing catalog permission. Run it against a dedicated validation database. It forwards the frontend HTTP requests to the specified real API, verifies creation and material persistence after reload, unchanged and changed specifications, clearing optional numbers, tri-state values, conflicts, wrong-parent access and deletion restrictions. Screenshots are written to `/tmp/nasa-spacecraft-e2e` by default.

## Completed validation

- Both migrations applied to the development PostgreSQL database and isolated validation databases.
- Catalog migration downgrade and upgrade verified on the isolated test database.
- Full backend suite with PostgreSQL integration enabled: 285 passed, 1 unrelated health-alert concurrency test skipped.
- New spacecraft API cases: 34 passed against PostgreSQL, covering capacity, validation, persistence, permissions, scoped access, duplicate codes, PATCH replacement and database constraints.
- All 9 frontend test files passed, including form preservation, clearing optional values, materials and maximum crew capacity.
- TypeScript checking and Vite production build passed.
- Alembic check found no differences between migrations and model metadata.
- Chromium completed the real-API UI flow, including creation and editing of maximum crew capacity, materials, reload, specification edits, conflicts, deletion and a 390px mobile viewport without horizontal page overflow.
