# Nasa Health Monitor

FastAPI backend using Python 3.13, PostgreSQL 17, SQLModel, and Alembic.

The Compose project name is fixed to `nasa`, so running `docker compose up` from
this directory uses `nasa_postgres_data`. The default directory name `back`
can select an unrelated older volume (`back_postgres_data`, PostgreSQL 13).
Do not delete that volume to resolve a version mismatch.

## Banco do monitoramento nesta instalação

A variável `NASA_DATABASE` em `.env` seleciona o banco usado pela API; quando
omitida, a API usa `POSTGRES_DB`. O banco selecionado deve existir. Nesta máquina,
`nasa_front_validation_20261111` contém o monitoramento já migrado. `app_db`
contém tabelas de outro sistema e uma revisão Alembic ausente neste projeto;
ele deve permanecer separado. Veja [DEMO.md](DEMO.md) para a conta e os cenários
fictícios de demonstração.

## Fresh installation

After cloning, run from the repository root:

```bash
cp .env.example .env
docker compose up --build -d
```

For an existing installation, preserve `.env` and run only the second command.
The database health check gates API startup. `scripts.startup` waits for the
database, applies all Alembic migrations, imports `knowledge_seed.json`, and only
then starts Uvicorn. Setup is serialized with a PostgreSQL advisory lock. If
migration or import fails, the API does not start. Logs are available with:

```bash
docker compose logs -f api
```

- API: http://127.0.0.1:8000
- OpenAPI UI: http://127.0.0.1:8000/docs
- Database hostname inside Docker: `db`; outside Docker: `127.0.0.1:5432`.

The fixture, scripts, and Alembic files are copied into the image. Initial loading
uses PostgreSQL and the local JSON file; it never contacts NASA or Ollama. An AI
provider is needed only when an assessment endpoint requests generation.
Repeated setup inserts missing records and leaves existing titles, summaries,
sections, tags, source metadata, and import timestamps unchanged. It does not
refresh or overwrite local edits. New seed revisions must use new stable IDs.

The PostgreSQL volume survives `docker compose down`. Initial database credentials
apply only to a new volume. Do not remove volumes to resolve migration errors.

### Existing database migration history

The pre-existing application database on this development machine references
Alembic revision `7efe7ee6f54f`, which is absent from this checkout. It was left
untouched. Restore the missing migration history before restarting setup against
that database; do not stamp it to bypass the mismatch. Fresh databases were
verified separately and do not have this issue.

## Public NASA reference knowledge

`knowledge_documents` contains source metadata, document type, UTC import time,
a stable ID, and an explicit public flag. `knowledge_passages` contains a stable
ID, document foreign key, section, optional 1-based PDF page, summary, and
PostgreSQL `text[]` topic codes indexed with GIN. The incremental migration
`c4e5f6071829` adds identity, type, and public scope to the original knowledge
schema without replacing existing rows. Both knowledge migrations are reversible.

A document is unique by stable ID and by source URL plus revision. A curated
passage is unique by stable ID and by document plus section. Stable IDs in the
versioned fixture are deterministic keys derived from source/revision and
section; they are persisted and must remain unchanged when editing the text.
They are identity keys, not content-integrity hashes. Numerical database IDs
remain internal foreign keys and are never part of an export.

`knowledge_seed.json` contains seven documents and eleven summaries written in
our own words. All source pages/PDFs were checked; no source is pending:

| Source | Type | Revision and summary location |
| --- | --- | --- |
| [CO2, OCHMO-TB-004](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf) | `technical_brief` | Rev D, 2026-03-10; Background / CO2-Induced Headaches, page 5 |
| [HRR SANS risk](https://humanresearchroadmap.nasa.gov/Risks/risk.aspx?i=105) | `risk_summary` | Last Published 2025-05-13 12:40:12 PM (Central); Risk Statement / HSRB State of Knowledge |
| [Health and Medical Care](https://www.nasa.gov/reference/3-0-health-and-medical-care/) | `technical_standard` | Volume 1, Revision C web edition; sections 3.2, 3.3, and 3.5 |
| [Appendix E](https://www.nasa.gov/reference/appendix-e-health-and-medical-care-technical-requirements/) | `technical_standard` | Volume 1, Revision C web edition; Table E.2-2, separate summaries for space motion sickness, adaptation-related back pain, and EVA dehydration |
| [Sleep Accommodations, OCHMO-TB-041](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-041-sleep-accommodations.pdf) | `technical_brief` | Rev B, 2023-10-23; Executive Summary, page 1 |
| [Exercise Overview, OCHMO-TB-031](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-031-exercise-overview.pdf) | `technical_brief` | Dated 2023-10-02; no revision label identified; Executive Summary, page 1 |
| [Food and Nutrition, OCHMO-TB-013](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-013-food-and-nutrition.pdf) | `technical_brief` | Cover says Rev E; body footers say Rev D, 2023-12-07; Executive Summary, page 1 |

Exercise and nutrition were located through the official
[Fundamentals of Human Health collection](https://www.nasa.gov/reference/fundamentals-of-human-health/)
and registered as separate briefs. The SANS source is a risk overview, not its
linked evidence report, so it is labeled `risk_summary`. Web sources have no PDF
page number. The food brief's conflicting revision labels are retained explicitly
rather than resolved by assumption. The SANS browser fetch timed out; a direct
HTTPS download of the official page succeeded.

These sources supply background context. They do not diagnose individual reports
or replace mission protocol decisions about urgency and treatment.

## Manual setup, import, and export

To rerun the same database preparation used during normal startup:

```bash
docker compose exec api python -m scripts.setup
```

To apply migrations or load only the versioned seed manually:

```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m scripts.seed_knowledge
```

Export the public reference base to a file in the mounted repository:

```bash
docker compose exec api python -m scripts.knowledge export /app/knowledge_export.json
```

Import that file with the same format:

```bash
docker compose exec api python -m scripts.knowledge import /app/knowledge_export.json
```

To import the shipped fixture explicitly:

```bash
docker compose exec api python -m scripts.knowledge import /app/knowledge_seed.json
```

The versioned JSON format has `format_version: 1` and a `documents` array. Each
document nests its passages and includes stable IDs, type, source metadata, and
an optional timezone-aware `imported_at`. Export supplies timestamps; import
preserves them, or generates a UTC timestamp for a new document when omitted.
Nested stable document/passage IDs preserve links across installations with
different numerical primary keys. Only explicitly public knowledge documents and
their passages are selected. Users, credentials, medical records, exams, and
assessments are not queried or exported. Unknown JSON fields and invalid or
duplicate identities are rejected by Pydantic.

Imports run in one transaction, add only missing records, and do not delete or
overwrite existing references. Conflicting identities abort the transaction.
A local edit stays local when the same fixture or export is imported again. To
transfer those edits to another installation, export and import into a migrated
empty knowledge base. Use an export as the backup before any deliberate local
reference changes.

For another existing database, pass its name to `exec`, for example:

```bash
docker compose exec -e PGDATABASE=another_database api alembic upgrade head
docker compose exec -e PGDATABASE=another_database api python -m scripts.knowledge import /app/knowledge_export.json
```

The named database must already exist. These commands reuse the project's PG
connection settings; they do not copy or initialize application data.

## Retrieval and assessment context

`KnowledgeRepository.find_by_symptom_codes` searches relevant tags among public
references and returns up to four distinct excerpts, ordered by passage ID.
Missing or unmatched codes return an empty list. Each result includes `source_id`
(`nasa:<stable_passage_id>`), title, `source_url`, revision, section, page, and
content. Source IDs now use persisted stable keys rather than installation-local
numerical IDs.

The demo accepts optional `confirmed_symptom_codes`. Supply only codes confirmed
by the assessment caller; neither free-text reports nor model output confirm
codes automatically:

```bash
curl --fail-with-body http://127.0.0.1:8000/demo/assessments/extract \
  -H 'Content-Type: application/json' \
  -d '{"context":"Senti dor de cabeça depois do treino","confirmed_symptom_codes":["headache"]}'
```

The service sends the report, confirmed codes, and `reference_excerpts` before
calling `AiProvider.generate`. Generated JSON is Pydantic-validated, and cited
IDs are checked against exactly the excerpts sent in that call. Unsent IDs are
rejected with 502. Urgency and treatment remain the mission protocol's
responsibility; this extraction demo has no clinical protocol engine.

The asynchronous provider interface remains independent of the reference store.
The OpenAI-compatible adapter uses one HTTP client during the FastAPI lifespan,
`AI_BASE_URL/chat/completions`, `AI_MODEL`, and an optional bearer token. The system
message loads `agent_instructions.md`. Invalid input returns 422; provider timeout
returns 504, provider unavailability 503, and invalid output 502.

Local Ubuntu AI defaults in `.env.example` are:

```dotenv
AI_BASE_URL=http://127.0.0.1:11434/v1
AI_MODEL=qwen2.5:3b
AI_API_KEY=
AI_TIMEOUT_SECONDS=60
```

Compose uses `http://host.docker.internal:11434/v1`, with a Linux host-gateway
mapping. Override it through `AI_DOCKER_BASE_URL`. Ollama on Ubuntu must listen on
an interface reachable from Docker. See the
[official Linux configuration](https://docs.ollama.com/faq#setting-environment-variables-on-linux).
Ollama configuration does not affect schema setup or reference loading.

## Verification

Development checks used initially empty PostgreSQL databases
`nasa_knowledge_setup_v2` and `nasa_knowledge_import_v2`; the original application
database was preserved. The checks cover:

- Setup twice: seven documents and eleven passages, with stable IDs and timestamps
  and no duplicates.
- Retrieval for `headache`, `blurred_vision`, and `fatigue`, empty results, and the
  four-excerpt limit; reference validation through a fictional AI provider.
- Preservation of local metadata, section, content, and tag edits on reimport.
- Public-only export, exclusion of nonpublic references, and atomic rejection of
  identity conflicts.
- Export to JSON, import into the second empty migrated database, and identical
  re-export including metadata, timestamps, tags, stable IDs, and document links.
- Incremental upgrade/downgrade preserving pre-existing references; GIN, `text[]`,
  foreign keys, and `alembic check` alignment.
- Docker image startup without the repository mount, using its packaged fixture
  with an unreachable AI endpoint; all three requested tag lookups succeeded.

Run tests in a dedicated migrated development database:

```bash
docker compose exec api pip install pytest
docker compose exec -e PGDATABASE=nasa_knowledge_setup_v2 api python -m scripts.setup
docker compose exec -e PGDATABASE=nasa_knowledge_setup_v2 \
  -e KNOWLEDGE_POSTGRES_TESTS=1 api pytest -q
```

Do not point PostgreSQL integration tests at a production database; they commit
the seed. Without `KNOWLEDGE_POSTGRES_TESTS=1`, those tests are skipped and unit and
authentication tests retain their temporary SQLite setup.

## Preflight examinations

Migration `d5f60718293a`, after `c4e5f6071829`, adds `missions`,
`mission_members`, `exam_types`, `mission_exam_requirements`, `astronaut_exams`,
`exam_results`, and `exam_result_reviews`. It uses integer keys like `users`,
PostgreSQL `timestamptz` for every timestamp, checks for roles/decisions/nonnegative
deadline offsets, unique mission/user and mission/type pairs, and composite
foreign keys enforcing that checklist members and requirements belong to the
same mission. All seven tables are registered with Alembic.

### Setup and authentication

Normal startup applies this migration automatically. To upgrade a running
installation with a consistent migration history explicitly:

```bash
docker compose exec api alembic upgrade head
```

For a fresh checkout, use the setup command at the start of this README. The
pre-existing development database's missing migration revision still needs to be
restored before this upgrade can be applied there; its history is not stamped or
reset by this module.

All preflight routes require the existing bearer token obtained from
`POST /v1/auth/login`. Since this repository has authentication but no global
administrator role, an authenticated user can create a mission and becomes that
mission's first `mission_admin` in the same transaction. The request cannot assign
an arbitrary initial administrator. The mission must always retain at least one
administrator. Existing admins manage later memberships; one role is allowed per
user per mission.

| Role | Configuration and checklist | Clinical results and review notes |
| --- | --- | --- |
| `astronaut` | Read mission configuration and own checklist | Read own results and reviews; cannot record or review |
| `flight_surgeon` | Read own mission's configuration and all its checklists | Read, record, correct unreviewed results, and append reviews in the same mission |
| `mission_admin` | Manage own mission, memberships, requirements, and scheduling; read checklist metadata | No access to clinical summaries or review notes through these routes |

Exam types are a shared, nonclinical catalog. Any authenticated user can read it;
a `mission_admin` of at least one mission can maintain it. Deactivation preserves
existing requirements and history but prevents adding new requirements using that
type. Codes already used by requirements cannot change, and used types cannot be
deleted. This shared catalog policy is separate from mission-scoped clinical
permissions. Roles in another mission never grant access to a target mission.

### Routes

All paths below have the `/v1` prefix. Lists use the existing `data` and
`pagination` structure, with `page` starting at 1 and `per_page` from 1 to 100.
New resources return 201, successful deletions 204, forbidden role operations 403,
unknown or inaccessible missions 404, protected-history conflicts 409, and invalid
input 422. Repeating identical member/requirement creation returns the existing
resource without duplicating checklist items; conflicting payloads return 409.

| Methods | Path |
| --- | --- |
| POST, GET | `/missions` |
| GET, PATCH, DELETE | `/missions/{mission_id}` |
| POST, GET | `/missions/{mission_id}/members` |
| GET, PATCH, DELETE | `/missions/{mission_id}/members/{member_id}` |
| POST, GET | `/exam-types` |
| GET, PATCH, DELETE | `/exam-types/{exam_type_id}` |
| POST, GET | `/missions/{mission_id}/exam-requirements` |
| GET, PATCH, DELETE | `/missions/{mission_id}/exam-requirements/{requirement_id}` |
| GET | `/missions/{mission_id}/astronauts/{member_id}/exams` |
| GET, PATCH | `/missions/{mission_id}/astronaut-exams/{exam_id}` |
| POST, GET | `/missions/{mission_id}/astronaut-exams/{exam_id}/results` |
| GET, PATCH | `/missions/{mission_id}/exam-results/{result_id}` |
| POST, GET | `/missions/{mission_id}/exam-results/{result_id}/reviews` |
| GET | `/missions/{mission_id}/astronauts/{member_id}/exam-types/{exam_type_id}/latest-accepted` |

`member_id` identifies a `mission_members` row, not a user. `exam_id` identifies an
`astronaut_exams` checklist item. PATCH of that item accepts only `scheduled_at`,
including null to clear the appointment. Callers cannot set `due_at`, checklist
state, authors, or audit timestamps.

### Checklist and history rules

Creating a requirement generates items for existing astronauts. Adding an
astronaut generates items for existing requirements. Both execute in the same
transaction as the initiating operation. Mission row locks serialize changes,
while uniqueness protects against duplicate checklist items.

Deadlines are `planned_launch_at - due_days_before_launch`. Changes to launch time
or requirement offsets recalculate open items. Completed items retain their
previous deadline; if a new realization or review reopens one, it uses the current
mission deadline. Performed and recorded timestamps on historical results remain
unchanged. A schedule alone does not complete an exam.

The most recent realization is ordered by `performed_at`, then `recorded_at`, then
ID. Each realization's latest review is ordered by `reviewed_at`, then ID:

| Condition | Checklist state |
| --- | --- |
| No result and no appointment | `pending` |
| No result and an appointment exists | `scheduled` |
| Latest result has no review | `awaiting_review` |
| Latest result's last review requests repetition | `repeat_requested` |
| Latest result's last review accepts it | `completed` |

`is_overdue` is separate and true only when the deadline has passed and the item
is not completed. Checklist responses expose identifiers, scheduling, requirement,
state, and overdue metadata; they exclude clinical summaries and review notes.

Only a mission's flight surgeon can create results or reviews. Result authors and
reviewer memberships come from the authenticated session. Result timestamps must
include a timezone and cannot be in the future or later than the actual mission
start when one is set. Corrections are permitted only before any review exists;
after review, record a new realization. Reviews are append-only, and later reviews
supersede earlier decisions without modifying them. There are no DELETE routes
for results or reviews.

Memberships and requirements with clinical history cannot be deleted or reassigned
to erase that history. Empty checklist items can be removed along with their
membership or requirement. Reviewer memberships used in history cannot be deleted
or change role. A mission can be deleted only after its configuration is removed,
leaving its sole administrator. These restrictions complement foreign keys with
no destructive cascades.

The `latest-accepted` response returns `latest_accepted_result`, `latest_result`,
`latest_review` for the latest realization, `latest_result_state`, and
`newer_result_requires_review`. It considers only the last review of each result,
so an earlier acceptance later superseded by `repeat_requested` is not treated as
accepted. A newer unresolved realization is explicitly flagged even when an older
accepted result is available. Without any accepted result, the accepted field is
null and an unresolved latest result is also flagged.

No attachment mechanism exists in this repository, so file uploads are outside
this module. Structured health measurements, flight clearance decisions, and
integration of this clinical history into the AI context remain later work. The
public NASA export still selects only public reference tables.

### Preflight verification

PostgreSQL checks used separate development databases `nasa_preflight_validation`
and `nasa_preflight_migration`. No existing application data was changed.
The complete suite passed with 50 tests. Verification includes:

- Upgrade from the prior four-table application schema plus Alembic metadata;
  populated-schema downgrade back to `c4e5f6071829`, followed by upgrade again.
  Existing users and NASA references were preserved, and `alembic check` found no
  model/schema drift.
- Fictional visual exam: mission and requirement, astronaut membership, first
  realization, correction before review, repetition request, second realization,
  acceptance, and retrieval of the accepted exam and complete history.
- Both orders of requirement/member creation and repeated operations without
  checklist duplicates; generation failures roll back the initiating membership.
- Role enforcement, author spoofing rejection, cross-mission and other-astronaut
  denials, clinical-data exclusion from admin views, last-admin protection, and
  direct SQL rejection of mismatched mission foreign keys.
- Open-item deadline recalculation, completed-item preservation, overdue state,
  latest-review semantics, later pending results, backdated realizations,
  deactivation, CRUD, pagination, and protected-history deletion conflicts.

Run against a dedicated database that already exists:

```bash
docker compose exec -e PGDATABASE=nasa_preflight_validation api python -m scripts.setup
docker compose exec api pip install pytest
docker compose exec -e PGDATABASE=nasa_preflight_validation \
  -e PREFLIGHT_POSTGRES_TESTS=1 -e KNOWLEDGE_POSTGRES_TESTS=1 api pytest -q
```

Preflight integration fixtures use real JWT authentication and PostgreSQL
transactions rolled back after each test, with only fictional users and clinical
content. Without `PREFLIGHT_POSTGRES_TESTS=1`, these integration tests are skipped.

### Account profiles

Migration `e6f718293a4b` adds independent `is_astronaut` and `is_physician` flags to users. Registration accepts either or both and rejects an explicit selection of neither. Legacy registration payloads default to astronaut; existing database users remain unclassified. Both flags are included in registration and directory responses. These account profiles do not grant mission permissions or change mission membership roles.

### Physician-only examination changes

All exam catalog, requirement, scheduling, result and review writes now require `is_physician=true` in addition to mission authorization. Flight surgeons may manage requirements and schedules; physicians who administer a mission retain these configuration permissions. Catalog writes require an administrator or flight surgeon membership. Astronaut-only accounts cannot bypass this restriction by obtaining another mission role. Indirect checklist generation, removal and deadline recalculation also enforce the physician requirement. Existing accounts without a physician profile remain unable to write examinations. Historical results and reviews still have no delete endpoints.

## Astronaut health monitoring

Health monitoring adds append-only observations, authenticated summary and filtered history endpoints, and individual preflight references. See [implementation, permissions, execution and validation](../HEALTH_MONITORING.md). Migration `f718293a4b5c` follows the account-profile migration. Self monitoring does not grant permission to modify preflight examinations.


## Structured exam catalog

Migration `f37e8091a2b3` adds exam definitions, versioned field snapshots and
structured results. Existing exam types, requirements and summary-only results
remain valid. A mission can now require multiple exams of the same type.

```bash
docker compose exec -T api alembic upgrade head
docker compose exec -T api python -m scripts.seed_exam_catalog
```

The optional seed adds 29 exams and 9 type categories based on
[NASA OCHMO-STD-100.1A, Revision A, September 2024](https://www.nasa.gov/wp-content/uploads/2024/09/ochmo-std-100-1a-rev-a-signed.pdf),
Tables 2–6 and the relevant mission evaluation sections. It preserves existing
records by code, including physician customizations. It creates definitions,
without assigning exams or fabricating patient results. Fields and units adapt
the reference for data entry; source page/section and revision remain visible.
No automatic fitness decision, clinical reference interval or mission schedule
is inferred. Laboratory reference intervals are recorded from the actual report.

Authenticated catalog routes:

- `GET /v1/exams`: `search`, `exam_type_id`, `is_active`, `page`, `per_page`.
- `POST /v1/exams` and `GET /v1/exams/{id}`.
- `PATCH /v1/exams/{id}`: complete definition plus `expected_revision`.
- `DELETE /v1/exams/{id}`: linked definitions return 409; inactivate instead.

Writes require a physician assigned as a flight surgeon or mission administrator.
Definitions contain number, short text, long text, selection, boolean and date
fields, with unique English identifiers, Portuguese labels, optional units and
required flags. Duplicate codes/options, empty names, unknown types, invalid
values and stale revisions are rejected.

Existing mission requirement routes accept `exam_definition_id` alongside
`exam_type_id`. They must refer to the same type. Assignments freeze the
field definition at generation. Catalog changes affect future assignments;
existing assignments and results retain their version. A requirement with
results cannot change exam. The legacy type-only requirement remains supported.

Existing result creation and correction routes accept `structured_values`,
`reference_ranges`, `collected_at`, `laboratory`, `performer_name`,
`sample_identifier`, `method` and `report_reference`, plus `performed_at` and
`summary`. Unknown fields, incompatible data types, missing required values,
invalid selection options and collection after performance return 422 atomically.
Only the mission flight surgeon with a physician profile can write results or
reviews. Astronauts can read only their own results and reviews. Mission
administrators cannot read clinical results. Reviewed results remain immutable;
register a new realization to preserve the existing review workflow.

For types with multiple assigned exams, pass the checklist exam ID to
`GET /v1/missions/{mission_id}/astronauts/{member_id}/exam-types/{type_id}/latest-accepted?exam_id={astronaut_exam_id}`.
An ambiguous type-only lookup returns 409. The existing preflight date rule
remains: a result must have been performed before mission start, when configured.

In the frontend, use **Exames** to manage definitions and result fields. In
**Missões → Requisitos**, choose a catalog exam and a deadline; the existing
checklist assigns it to astronaut members. In **Checklist → Histórico**, the
flight surgeon records structured results and reviews, while the astronaut has
a read-only view of their own records. Correcting a reviewed result is hidden.

Verification in a temporary PostgreSQL database, including upgrade/downgrade
with existing results and the complete backend suite:

```bash
docker compose exec -T api python -m scripts.verify_exams
```

The command needs pytest installed in the API development environment. It
creates and drops its own database and does not use patient data. Frontend
checks run with `npm test` and `npm run build` in the frontend repository.
