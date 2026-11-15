# Medications and allergies

The medical record uses the astronaut's user as the clinical identity. Allergies reference `users.id` through `crew_member_id`, regardless of the mission. The `users.allergy_screening_completed` field starts as `false`, including for existing users. The mission provides the flight surgeon's authorization context, without limiting allergies to that mission.

Authenticated users can view the catalogs. Editing them requires a physician assigned to a mission as `mission_admin` or `flight_surgeon`, as for exam types. Astronauts view their own allergies. Viewing by others and editing require the flight surgeon assigned to the astronaut's mission, given in `mission_id`.

## Routes

All routes use the `/v1` prefix and require authentication.

| Resource | Operations |
| --- | --- |
| `/medicines` | Paginated GET, POST |
| `/medicines/{medicine_id}` | GET, PATCH, DELETE |
| `/active-ingredients` | Paginated GET, POST |
| `/active-ingredients/{ingredient_id}` | GET, PATCH, DELETE |
| `/health/astronauts/{crew_member_id}/allergies` | GET, PUT; optional `mission_id` parameter |

Listings accept `search`, `page` and `per_page` (maximum 100) and return `data` and `pagination`.

Medication POST and PATCH accept `name` and `active_ingredient_ids`. The composition is returned as `active_ingredients`, with IDs and names. In PATCH, omitting the composition keeps it; sending `[]` removes it. Name and composition are saved in the same transaction.

The allergies PUT requires `allergy_screening_completed` and accepts `active_ingredient_ids` (empty list by default). This operation replaces the complete record in the same transaction. Duplicate or nonexistent IDs are rejected. Deleting an active ingredient in use returns HTTP 409.

## Screens

Navigation includes Medications and Active ingredients, with search, pagination, creation and editing. A medication can have several active ingredients. The Allergies section is in health monitoring and in the mission medical record. Write controls follow the permissions returned by the backend.

Open screening always appears as “Screening pending”. Completed screening appears as “Allergies recorded” when there are items and “No known allergies” when there are none.

## Migration

From `back/`, with the Docker environment configured:

```sh
docker compose exec -T api alembic upgrade head
```

Outside Docker, with `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGPORT` and `PGDATABASE` set:

```sh
alembic upgrade head
```

The revision is `a8293b4c5d6e`, after `f718293a4b5c`.

## Verification

From `back/`, with the backend dependencies and pytest installed:

```sh
python -m pytest -q
python -m pytest -q tests/test_medicine_service.py tests/test_medicines.py
```

Service tests use SQLite with foreign keys enabled and cover multiple ingredients, editing, rollback, search, pagination, validation, permissions, screening and deletion blocking. API tests cover these flows over HTTP, and the migration test checks that existing records start with pending screening. The existing PostgreSQL tests require an isolated, migrated database and `PREFLIGHT_POSTGRES_TESTS=1`.

From `front/`:

```sh
npm test
npm run build
```

The allergy tests check the four combinations of screening state and presence of allergies.

## Initial catalog and main indications

Revision `b93a4c5d6e7f` adds `medicines.main_indications` as optional text. The field is accepted in medication POST/PATCH, returned in queries and editable in the frontend. In PATCH, omitting it keeps the value and sending `null` clears it.

The catalog and its provenance are in `back/data/common_medicines.json` and `back/data/README.md`. The selection has 100 items per country, with 161 medications and 160 distinct active ingredients after deduplication. The Brazilian list is a selection of common use, not an official ranking. Names and indications are in English; revision `5b3c4d5e6f72` converts databases seeded with the earlier Portuguese catalog.
