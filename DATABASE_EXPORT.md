# Application database export

The preparation replaces demonstration labels with plausible fictional names and keeps the generated origin in an external record. It does not give the data clinical or historical authenticity. Reference documents and technical protocol/origin codes stay as originally recorded.

The active database keeps 56 missions: 50 from the generated history and 6 earlier ones. The new missions go from Aurora 01 to Cruzeiro 05. In the interface, Rafael Andrade has the Mission administrator profile and Helena Monteiro has the Physician profile.

## Prepare names

From `back/`, first back up the database, then run:

```bash
docker compose exec -T -e SALUS_SYNTHETIC_ENV=development api python -m scripts.prepare_database_export
```

The script uses `data/synthetic_missions_public/manifest.json` to check the 50 IDs and records the mapping between previous and current names in `data/synthetic_missions_public/presentation.json`. The record stays outside the database and contains the original configuration and the data origin. Repeated runs check the IDs and names and do not recreate or rename the set again. The `--publish` generator also uses this record to avoid duplication after the names change. Keep these files when you continue development.

Crew names are deterministic and contacts use the reserved domain `crew.salus.example`. Replacements in JSON snapshots preserve numeric values, dates and ID references. Documentary sources are not rewritten. Technical fields such as `profile_id`, `rule_version`, codes and telemetry origin are preserved. The preparation requires a development or test environment and is transactional.

The generated names are proper names (for example `Atlântico 03` or `João Almeida`). The script matches them exactly on repeated runs, so they are not translated.

## Export

The local package is in `back/exports/`. To repeat the export, replace `YOUR_DATABASE` with the database configured for the API:

```bash
mkdir -p exports
docker compose exec -T -e SOURCE_DATABASE=YOUR_DATABASE db sh -c 'pg_dump -U "$POSTGRES_USER" --no-owner --no-acl --schema=public -Fc "$SOURCE_DATABASE"' > exports/salus_database.dump
```

The export includes every table and record of the application schema, sequences, functions, indexes, constraints, PDFs, passages and the Alembic revision. Auxiliary validation schemas are left out, which avoids duplicating the history. Environment credentials are not exported. The existing user and permission records are part of the requested database.

The `salus_database_20261115.zip` package contains the PostgreSQL dump, restore instructions, SHA-256 hashes, the external origin manifest and the result of the restore check.

## Checks performed

- The API returned HTTP 200 and the 50 missions with the new names for Rafael Andrade; the 6 earlier missions are still present.
- Comparison with the backup: 189,691 records in 62 tables, with no changes to numeric values, source dates, keys, links or binaries. The time of the worker's automatic recommendation enrichment was excluded from this comparison.
- The dump was restored into another PostgreSQL database and checked against the 50 IDs, names and balances of the history and the 56 total missions.
- Tests: `tests/test_database_export.py` and `tests/test_synthetic_missions.py`, with `PREDICTIVE_POSTGRES_TESTS=1`: 9 passed. Python compilation and `git diff --check` passed.

The name mapping and the expected outcomes stay out of the recommender inputs. The earlier metrics remain functional checks with generated data, not clinical validation.
