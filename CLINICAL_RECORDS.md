# Individual health records and NASA assessments

## User flow

Open **Astronaut control → Overview** or **Health monitoring** and select a mission and astronaut. The **Health problems & medication use** section supports these flows:

1. **Report a health problem**: search the complete local WHO ICD-10 2019 English tabular catalog by code or name, or describe a problem without a code. Enter symptoms, description and **Start at**. Nonterminal classification categories remain searchable but cannot be recorded as a specific condition. The selected official label is resolved by the backend.
2. Active problems appear first. An astronaut also sees their active problems in a sticky banner across application navigation. Refreshing preserves the banner; it polls every 30 seconds and refreshes after local changes. A reported code is not a confirmed diagnosis.
3. **Confirm recovery** is available only to another physician assigned as the mission's flight surgeon. Record **Finish at** and a recovery assessment. The record remains in history with the physician and recording timestamps. Recovery cannot precede onset or occur in the future. A second recovery cannot overwrite the first.
4. **Record medication taken**: select an existing medication; record when it was taken, dose and route, reason, and who instructed the consumption. The instruction field accepts a name/role or an explicit self-directed report; it is not a verified prescription. The astronaut and recording actor are separate identities. An optional health occurrence must belong to the same astronaut and mission. Consumption records are append-only and retain the original medication name after catalog edits.
5. **Current individual health report** combines current/previous observations, quality and activity context, active clinical alerts, active reported problems, recent medication consumption and actual mission day. Future launch plans are not treated as actual mission exposure. Missing measurements and freshness limits remain explicit.
6. An assigned flight surgeon can **Generate NASA health assessment**. The server retrieves indexed public NASA passages using the existing Ollama RAG service. It submits recent good-quality physical observations and mission day, with no names, user IDs, free-text medical histories, medication narratives or private psychological records. Mood and attention are excluded from generation. Each hypothesis must cite supplied observation IDs and retrieved passage IDs. Empty, invalid or unavailable generation produces an explicit result and preserves the factual report.
7. Generated assessments remain pending until the flight surgeon approves or rejects them with a note. Astronaut queries return approved assessments only. Approved hypotheses appear in the astronaut's top banner with the assessment date and physician review. The original clinical alert workflow remains immediate and independent of AI.

The interface retains the existing English labels and components. Clinical access reuses `HealthService.authorize`: astronauts access only themselves; assigned flight surgeons and nurses access only the astronaut in their mission. Operational/global administrators do not receive clinical access from administrative status. Nurses cannot confirm recovery, generate assessments or approve hypotheses.

## Sources and limitations

WHO's original English ZIP is retained in `back/data/icd10_who/icd102019enMeta.zip`. `catalog.json` pins its official URL, revision, archive member date, SHA-256 and byte count. Text files are not paginated, so page count is null. This is WHO ICD-10, not ICD-10-CM or ICD-11. The catalog includes disease, symptom, injury and other classification codes; it is not a list restricted to diseases.

NASA originals and provenance are retained under `back/data/nasa_references/`, including the crew health standard, historical medical care, CO2, urinary health, venous thrombosis, sleep, exercise and behavioral references. The source catalog records exact revisions rather than assuming the copies are the latest NASA revisions. Generated assessments retain retrieved excerpts, page numbers, revision, official URL and passage identity.

No validated individual disease-probability model is configured. No numerical probability or date-specific disease forecast is produced. In particular, reaching day five does not generate a claim that headache is probable. The report distinguishes mission context from measurements and evidence. Model outputs are screening hypotheses requiring medical review. Existing configured clinical alert thresholds are unchanged. Symptom text and medication instructions are recorded reports, not AI prescribing inputs.

Freshness follows the existing mission alert profile per indicator. Generation uses indicators with a fresh good-quality latest reading and includes their previous reading only when it is also fresh and good quality. Both readings remain in the factual report. Poor/unknown-quality and stale readings cannot support generated hypotheses. Normal measurements do not exclude illness. The medication portion of a report includes the latest 30 consumption events; complete history remains accessible through the paginated endpoint.

NASA PDF extraction uses conservative chunk subdivision for dense punctuation/tables to reduce embedding context overflow without discarding source text or losing page provenance. This is an estimate, not an exact model tokenizer; extraction/index failures remain explicit and retryable. No OCR is added.

## Schema and API

Migration `2d9e3f405162`, following `1c8d2e3f4051`, adds `health_occurrences`, `medication_uses` and `clinical_assessments`. Existing observations, medication catalogs, mission occurrences and records remain intact. Clinical occurrences are individual medical reports; operational mission occurrences retain their original meaning.

All paths use `/v1/health`:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/icd10` | Search with `search`, `page`, `per_page` |
| GET/POST | `/astronauts/{id}/occurrences` | History or create a reported problem |
| POST | `/astronauts/{id}/occurrences/{record_id}/recover` | Physician recovery |
| GET/POST | `/astronauts/{id}/medication-uses` | Consumption history or append a record |
| GET | `/astronauts/{id}/clinical-report` | Current factual health report |
| GET/POST | `/astronauts/{id}/assessments` | Reviewed history or physician generation |
| POST | `/astronauts/{id}/assessments/{record_id}/review` | Physician approval/rejection |

Mutation payloads include `mission_id`; recovery/review use the positive query parameter `mission_id`. All event timestamps require an explicit timezone. List endpoints accept pagination and optional mission context. Another person's records always require mission context. `active=true` selects ongoing occurrences. Creation and review identities come from the current authenticated/public-profile actor, never a client-provided actor ID.

## Reproduction and verification

From `back/`:

```bash
docker compose up -d
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic check
docker compose exec -T api python -m pytest -q tests/test_clinical_records.py tests/test_health_alerts.py tests/test_medicines.py tests/test_medicine_service.py
docker compose exec -T api python -m scripts.index_nasa_references
docker compose exec -T -e MISSION_RISKS_POSTGRES_TESTS=1 -e MISSION_RISKS_REAL_OLLAMA=1 api python -m pytest -q tests/test_clinical_records.py tests/test_mission_risks.py
```

From `front/`:

```bash
npm test
npm run typecheck
npm run build
npm run test:clinical:e2e
```

Backend HTTP tests use synthetic isolated SQLite records with foreign keys enabled. They cover catalog pagination, invalid/nonterminal codes, timezone and future-date validation, clinical permissions, active history/recovery, medication provenance, mission day/current/previous measurements, Ollama failure, citation validation and medical approval. Browser verification uses synthetic HTTP responses and the actual React component at mobile width. It covers code selection, persistent active problems, consumption fields, physician recovery and assessment approval. It does not claim to validate a clinical prediction model.

## Verified results

- Targeted clinical/health-alert/medication/risk run: 131 passed; 15 optional PostgreSQL/real-model cases skipped in that run.
- Clinical and risk tests with isolated PostgreSQL and real Ollama enabled: 33 passed, including real clinical generation against the indexed NASA corpus. Synthetic person/mission records were confined to a temporary schema and removed afterward.
- Frontend Node tests: all 13 test files passed. TypeScript checks and production build passed. Mobile clinical browser flow passed.
- Live database is at revision `2d9e3f405162`; `alembic check` reports no new upgrade operations. The model now also declares the existing knowledge-index metadata index, preserving that index.
- NASA corpus import: all 12 retained PDFs passed hash/page verification, real embedding and page-aware retrieval (583 pages; 5,358 passages). Original files and source catalog remain local.

Remaining toolchain messages are the existing large Three.js bundle warning and the Starlette/httpx deprecation warning. Neither prevented these checks.
