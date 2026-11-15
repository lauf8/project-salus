# Mission risks — Project Salus

The first supported rule projects food shortages. Stock arithmetic, severity, comparable-history counts and dates are calculated by the backend. Ollama retrieves reference passages and suggests non-clinical operational actions. It does not calculate the forecast or confirm an occurrence.

## Repository and schema inspection

No existing root, backend or frontend `AGENTS.md` was found. The root file now records project conventions and confirmed commands.

Existing knowledge tables were reused:

| Table | Existing structure | Added for this flow |
| --- | --- | --- |
| `knowledge_documents` | Numeric ID, stable ID, title, source URL, revision, type, public flag, import timestamp; unique source/revision | PDF bytes, unique SHA-256, origin, indexing status/error, embedding model/dimension, chunk configuration, indexed timestamp |
| `knowledge_passages` | Numeric/stable IDs, document FK, section, page, text, topic codes; unique document/section, topic GIN index | Passage order, source section, floating-point embedding array |

Existing operational structures are also reused:

- `missions`, `mission_members`, `spacecraft`: mission, crew and vehicle. Mission membership and existing profile checks govern access. The existing public profile selector remains; this module does not add password authentication.
- `food_products`, `mission_food_lots`, `meal_logs`, `meal_log_items`, `food_stock_movements`: catalog, stock, expiration, consumption and immutable ledger. Meal logs already have `consumed_at` and `recorded_at`; movements have `recorded_at`. Lots have expiration but no separate receipt event timestamp; receipt availability is taken from their initial movement.
- `health_observations`, `health_alerts`, `health_notifications`: clinical monitoring. Clinical observations remain separate. Notifications now also support a risk-alert FK; clinical FKs are nullable only to support that alternative. Existing clinical inbox joins continue to include clinical alerts only.
- `nutrition_plans`: dated dietary guidance and nutrient targets, but no structured daily quantities by food. These free-text plans are not interpreted as numeric food demand.
- `app/core/ai_config.py`, the existing AI provider and Compose already configure an Ollama-compatible generation endpoint. RAG adds a native Ollama adapter with separate embedding and generation models.

New tables: `mission_risk_plans`, `mission_occurrences`, `mission_risk_evaluations`, `mission_risk_alerts`, `mission_risk_actions`.

`1c8d2e3f4051_mission_risks_rag.py` merges the existing heads `a0ef5678b920` and `0b7c1d2e3f40`, adds the fields above and creates the risk tables. Existing rows are retained. Legacy knowledge is initially `not_indexed`; existing passages can be indexed without a PDF. Existing stock rows are not assigned invented availability times.

New stock movements include an immutable `risk_snapshot`: signed reference quantity, event time, food name, expiration, reference quantity and unit. Reversals preserve the original event time and negate its original conversion. This supports meal edits and deletions without reading their current mutable state during replay. Existing catalog equivalences normalize stored/prepared quantities; planned inputs additionally accept kg and L when convertible to g and ml.

## Development and migration

From `back/`:

```bash
docker compose build api risk-worker
docker compose up -d
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic heads
```

Startup already applies migrations under the existing PostgreSQL advisory lock. The Compose project name remains `nasa` and uses the existing PostgreSQL 17 volume. A pre-migration local backup was saved to `back/backups/before_mission_risks_20261114.dump`; backups are not versioned.

From `front/`:

```bash
npm run dev
npm run build
npm test
npm run typecheck
npm run test:risks:e2e
```

## Ollama configuration

Configure through environment variables or an untracked `back/.env`. Do not commit credentials or machine-specific addresses.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | Outside Compose: `AI_BASE_URL` with `/v1` removed, or `http://127.0.0.1:11434` | Native API base |
| `OLLAMA_DOCKER_BASE_URL` | `http://host.docker.internal:11434` | Compose-to-host native endpoint |
| `OLLAMA_EMBEDDING_MODEL` | `all-minilm` | Index and query embedding model |
| `OLLAMA_GENERATION_MODEL` | `AI_MODEL`, normally `qwen2.5:3b` | Structured operational guidance |
| `OLLAMA_TIMEOUT_SECONDS` | `60` | Timeout per Ollama request |
| `RAG_CHUNK_SIZE` | `500` | Characters per page-preserving chunk |
| `RAG_CHUNK_OVERLAP` | `150` | Character overlap within each page |
| `RAG_MINIMUM_SIMILARITY` | `0.3` | Minimum cosine similarity for evidence |

Install models if missing:

```bash
ollama pull all-minilm
ollama pull qwen2.5:3b
```

The native endpoints are `/api/tags`, `/api/show`, `/api/embed` and `/api/generate`. Check **Risks → documents → Check Ollama models**, or `GET /v1/risk-documents/ollama`. Index and query use the same model and dimension. Changing model or chunk settings marks reindexing as required; mismatched dimensions are excluded at search time. Reindex to rebuild vectors if a model changes dimensions under the same name.

No PostgreSQL extension is required. Embeddings use PostgreSQL floating-point arrays and the migration installs `salus_cosine_similarity`. Search filters completed, public indexes by model, dimension, origin and optional document, then ranks exact cosine similarity in SQL. This is an exact scan after metadata filtering, suitable for the initial corpus; larger corpora will require a measured indexing/ANN migration.

Adapter references: [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md), [Ollama embedding API](https://github.com/ollama/ollama/blob/main/docs/capabilities/embeddings.mdx), [pypdf extraction](https://github.com/py-pdf/pypdf/blob/main/docs/user/extract-text.md).

## Import the first PDF

1. Open a mission and the **Risks** tab. Use an authorized mission administrator, nutritionist or flight surgeon; document indexing additionally uses existing food-catalog writer permissions.
2. Open **documents**. Enter a title, version and optional HTTPS NASA URL. Upload a selectable-text PDF of at most 20 MiB.
3. Click **Index / reindex**. The browser displays processing while extraction and Ollama indexing run synchronously. The persisted document state is queued, completed or failed; only committed completed indexes are searchable. The intermediate processing state belongs to the indexing transaction.
4. Search passages and inspect the returned numeric passage ID, page/section, title, revision, origin and URL.
5. If extraction or Ollama fails, the document remains recorded with a clear failure and **Retry processing**. Image-only PDFs require external OCR and import of a new revision; OCR is not included.

SHA-256 deduplicates identical uploads, including concurrent reimports. A different file with an existing source/revision is rejected; use a new revision. A legacy document without a PDF can receive its matching source/revision file without creating a second document. Reindexing preserves legacy passage identities and retires superseded PDF chunks from vector search.

The already registered **NASA OCHMO-TB-013 Food and Nutrition** reference was reused. Its official PDF URL is `https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-013-food-and-nutrition.pdf`; existing metadata distinguishes the cover revision from the body footer. It was attached to the existing reference and indexed with the real Ollama instance.

To create a clearly synthetic PDF for local verification:

```bash
docker compose exec -T api python -m scripts.create_risk_demo_pdf /tmp/salus-synthetic.pdf
docker compose cp api:/tmp/salus-synthetic.pdf /tmp/salus-synthetic.pdf
```

The fixture explicitly says it is synthetic and is not NASA operational guidance. Do not treat its content as an approved procedure.

## Reproduce the complete food-shortage flow

1. Create/select a mission and its crew in the existing mission UI.
2. Create a food product in **Food and beverages**, for example a product with a reference portion of 100 g and stored basis.
3. In the mission's **Food and hydration** stock view, register a usable lot with 600 g and an expiration after the mission end. Record an astronaut meal of 100 g through the existing meal form.
4. In **Risks → planning**, enter exposure start, an expected end eight days ahead, crew size two, and a planned daily demand of 100 g per person for that product. Declare inventory complete only if it is complete. Save.
5. The usable balance is five reference portions, daily demand is two portions, and the backend projects a shortage during the horizon. The exact shortage date follows the current UTC date and lot expiration. Open the alert to inspect its daily FEFO allocation, demand source/window, immutable input IDs and history counts.
6. If relying on recorded consumption instead of a planned food quantity, declare a complete observed interval covering the configured number of completed UTC days, ending at the current UTC midnight. A partially logged meal day is not silently treated as complete demand. If both sources exist, use the larger daily demand.
7. Retrieve preventive guidance. Only retrieved passage IDs may be cited. The deadline and severity remain backend values. An approved operational action registered in planning takes precedence; its procedure reference is shown. The daily worker also processes pending guidance.
8. Review generated guidance before astronaut delivery: choose **Approve generated guidance**, classify it as operational or clinical, and record the review. Clinical approval requires a physician. Unreviewed generated text is withheld from the astronaut; the safe stock-verification action remains available. Assign the action to an astronaut or authorized operational team member. On the astronaut's initial control view, **Your mission risk actions** opens the mission risk. Confirm reading and execution. The mission team records the final outcome and resolves the alert.
9. Register an actual prior shortage in the corresponding earlier mission's **occurrences** view. Supply event time, phase, source, severity, actions and outcome, then explicitly confirm it. Prediction or action completion never creates a confirmed occurrence automatically.

Current UI language remains English; the requested “Riscos” area is labeled **Risks** consistently with the rest of the interface.

## Projection and history rules

`food-fefo-v1` projects full daily demand from the next UTC day, or from planned exposure start if later, through expected mission end. Already consumed stock is not consumed again for the current partial day. Expiration date itself is usable; remaining quantities are discarded starting the next UTC date. FEFO uses earliest expiration, then lot ID. It never uses stock received after the evaluation cutoff. There is no automatic resupply assumption.

A complete inventory declaration permits an empty inventory to represent zero available stock; without that declaration it is inconclusive. Missing mission planning, unknown demand, incompatible conversions, ended horizon or conflicting crew planning are explicitly reported. Prior active alerts are preserved when updated data is insufficient. A newly sufficient projection resolves the active alert and logs the reason.

Critical means first shortage no later than three days after projection start; later shortages are warnings. All dates, signals, demand origins, calculation windows, plan/lot/movement IDs and comparison evidence are saved in `mission_risk_evaluations`.

Comparison considers prior completed missions with the same food and comparable crew size, duration, per-person demand and equivalent elapsed/remaining exposure. The initial comparability envelope is 0.5–2×. A mission with unknown demand or incomplete declared coverage is not counted as sufficiently covered. Observed demand may be used when immutable records and coverage exist. Coverage is a dated, authorized declaration, not a claim inferred from absence of an incident. The UI reports eligible, covered and affected mission counts separately: e.g. “1 of 2 comparable missions with sufficient data.” It does not claim a calibrated probability or causal effect.

Historical confirmation and record availability must precede the assessment cutoff. Cohort eligibility also requires a completed-mission snapshot saved in an evaluation by that cutoff; it never reads a later edit of a previous mission’s status/end date. Older missions without that availability evidence are excluded until an authorized dated assessment is recorded. Sources, actions, outcomes and intervention markers are retained with the counts. No compatible sufficient history is explicitly shown.

## Scheduling, concurrency and resilience

- Saving food planning calculates immediately, including preflight inventory.
- Existing stock/meal creation, correction and deletion recalculate within the existing transaction, without contacting Ollama.
- Mission metadata and crew mutations recalculate when risk planning exists. Changed crew-size planning must be updated explicitly rather than silently assuming a new plan.
- `risk-worker` checks once a minute, evaluates each eligible mission once per UTC day, and processes pending documentary guidance independently. It retries infrastructure failure on subsequent cycles.
- Run one cycle manually: `docker compose exec -T api python -m scripts.sync_mission_risks`.
- Mission-row locks serialize concurrent evaluations. A PostgreSQL partial unique index guarantees one active alert per mission/risk/product. Notification recipient uniqueness prevents repeated deliveries for the same alert.
- Repeated assessments refresh the alert's evidence state; prior calculated alerts and stock remain persisted if Ollama is unavailable. The worker's failed-generation result shows absence of documentary evidence; the next daily evaluation or manual request can retry it.
- Assignment, reading, execution, automatic resolution and final outcome are auditable action records. Reading marks the corresponding recipient's existing notification read.

## Chronological replay

For a completed mission, open **Risks → replay**, select start/end, and run. The same endpoint is `POST /v1/missions/{mission_id}/risks/replay` with timezone-aware `start_at` and `end_at`; the interval must be ordered, at most 730 days and no later than actual mission end.

Each daily prediction uses only planning versions and stock movements recorded by that cutoff, plus their immutable event/conversion metadata. Current mutable meal revision flags, catalog names/equivalences and future receipts are not used. Legacy movements without snapshots make historical evaluation inconclusive; no synthetic old availability is invented. Plans, stock or late historical confirmations registered today cannot retroactively influence yesterday's prediction.

Replay stores a `state='replay'` report in the existing evaluation table, separate from the current live assessment. The report records chronological inputs and signals, lead time, detected/missed confirmed occurrences, alerted foods without confirmed occurrences, and interventions. Full final outcome labels are used only for scoring, never as prediction input. An alert without a confirmed occurrence is not automatically called a false positive: intervention and incomplete follow-up are distinguished. Replay does not create/resolve live alerts, send notifications, retrieve documents or call generation.

## Permissions and data boundaries

Existing mission access checks are reused. Mission administrators, nutritionists and physician flight surgeons can plan/evaluate/confirm events. Observers cannot mutate risks. Astronauts see their assigned operational alerts and can read/execute them; only authorized team members assign and resolve. Document writes use existing food-catalog writer checks. Optional legacy bearer credentials remain accepted for older API callers; public-profile access remains available as requested for the application.

RAG receives only food name, shortage date, daily demand, risk category and aggregate history counts, alongside public reference excerpts. No health records, psychological narratives or person identifiers are sent. Sleep/fatigue, physical fitness, well-being and spacecraft rule slots report explicit unimplemented/data-insufficient dependencies; no clinical guidance is generated for those slots. All generated guidance is withheld from astronaut views until team review; a clinical classification requires a physician. Approved operational procedures and the built-in stock-verification action remain available.

## Verification

Install test dependencies in the container when necessary:

```bash
docker compose exec -T api pip install -r requirements-dev.txt
docker compose exec -T -e MISSION_RISKS_POSTGRES_TESTS=1 api python -m pytest -q
```

Risk PostgreSQL tests create a unique schema with no fallback to the public search path and drop it after each test. The test cosine function is copied from the actual migrated function. Only synthetic mission/person/food data is used. Do not point synthetic fixtures at production tables.

Real Ollama verification:

```bash
docker compose exec -T -e MISSION_RISKS_POSTGRES_TESTS=1 -e MISSION_RISKS_REAL_OLLAMA=1 api python -m pytest -q -s tests/test_mission_risks.py::test_real_ollama_pdf_index_search_and_generation
```

Tests cover selectable PDF import, duplicate imports, failed indexing/retry, image-only failure, page recovery, changed model exclusion, invalid citation rejection, FEFO and expiry, missing data, normalized units, concurrent alert/notification deduplication, permission enforcement, assignment/read/execution, explicit occurrence confirmation, history counts, future-record exclusion and the complete HTTP stock/meal/document/guidance/action flow.

The browser command `npm run test:risks:e2e` exercises the real React component with simulated API responses. It covers planning, alert detail/history, citations, multipart upload, failed/retried indexing, explicit event confirmation and astronaut execution permissions. It is distinct from backend PostgreSQL tests and from real Ollama checks.

Verified against a real instance: native model capabilities, 384-dimensional `all-minilm` embeddings, PDF indexing and page-aware retrieval, and structured `qwen2.5:3b` generation. Failure cases and concurrency use controlled simulated responses. The official existing NASA reference was also attached/indexed and searched against the real running API; synthetic generation verification remains labeled synthetic.

Final verification results: **296 backend tests passed, 82 skipped** in the complete suite with both `MISSION_RISKS_POSTGRES_TESTS=1` and `MISSION_RISKS_REAL_OLLAMA=1`. Skipped cases require other optional integration flags. The real Ollama case also passed when run separately. **13 frontend test files passed**, TypeScript checks passed, the production build passed, and the risk browser flow passed. The remaining build message concerns the existing large Three.js bundle. The backend emits a pre-existing Starlette/httpx deprecation warning.

## Changed files

- Project instructions and module documentation: `AGENTS.md`, `MISSION_RISKS.md`.
- Schema: `back/alembic/versions/1c8d2e3f4051_mission_risks_rag.py`, `back/alembic/env.py`, and models `mission_risks.py`, `knowledge.py`, `nutrition.py`, `notifications.py`.
- Backend flow: router/schema `mission_risks.py`; services `mission_risk_service.py`, `food_risk_rule.py`, `mission_rag.py`; nutrition/preflight transaction hooks; application router registration; optional legacy bearer compatibility in `dependencies/auth.py`.
- Configuration and utilities: `back/compose.yaml`, `back/requirements.txt`, `back/requirements-dev.txt`, `scripts/sync_mission_risks.py`, `scripts/risk_worker.py`, `scripts/create_risk_demo_pdf.py`.
- Interface: `front/src/MissionRisks.jsx`, `mission-risks.css`, mission/detail and astronaut entry points in `main.jsx`, mission tabs in `user-profiles.js`, multipart support in `services/api.js`, and the npm browser-test command.
- Verification: `back/tests/test_mission_risks.py`, frontend multipart/tab tests and `front/scripts/verify-mission-risks.mjs`. Existing clinical fixtures include the new notification dependencies; old no-login expectations were aligned with public access. Trend fixtures use deterministic daytime timestamps so same-day measurements do not cross midnight depending on when tests run.

## Synthetic mission with health alerts

The Risks alert view also displays existing clinical alerts through `GET /v1/missions/{mission_id}/risks/health`. No new clinical thresholds or disease-probability model were introduced. The view reuses `HealthAlertService` and existing health-record authorization: the assigned physician can inspect the mission's clinical alerts, astronauts can inspect only their own, and operational administrators receive an explicit restricted state instead of patient data.

`app/services/clinical_risk_context.py` supplies cautious screening labels and reference links for low glucose, low oxygen and fever. These are review signals, not diagnoses of diabetes, pneumonia, infection or another future disease. General information references: [NIDDK low glucose](https://www.niddk.nih.gov/health-information/diabetes/overview/preventing-problems/low-blood-glucose-hypoglycemia), [NHLBI respiratory symptoms](https://www.nhlbi.nih.gov/health/respiratory-failure/symptoms), [MedlinePlus fever](https://medlineplus.gov/fever.html). Clinical action remains in the existing health alert workflow; no patient data is sent to Ollama.

To add the explicitly synthetic demonstration without replacing existing missions or crew:

```bash
docker compose exec -T api python -m scripts.seed_risk_alert_mission
```

The script creates **Salus Alert Demonstration — Synthetic Data**, four dedicated fictional accounts, two astronaut memberships, a simulation-only health configuration, four synthetic observations and a food-stock scenario. It is idempotent and refuses account/crew conflicts rather than overwriting existing data. Notifications are internal records addressed only to the dedicated demonstration staff; it sends no external messages. It does not reuse or modify real patient records or existing spacecraft.

To view all demonstration alerts, refresh the app, select **Physician → Salus Demo Physician**, open **Missions**, find **Salus Alert Demonstration**, and open **Risks**. The initial scenario contains critical low-glucose and low-oxygen alerts, urgent temperature and resting-heart-rate alerts, and a projected food shortage. These measurements are explicitly labeled synthetic. Use **Open clinical alert** to inspect the original clinical workflow. Re-running the script does not reset acknowledged/resolved alerts or refresh old measurements silently.

Verification of this addition: mission creation/idempotence and physician/astronaut/administrator visibility are covered by `test_synthetic_alert_mission_is_idempotent_and_clinical_access_stays_scoped`; the risk test file passed **16 tests**, with the separately controlled real-Ollama test skipped in this targeted run. The browser risk flow, production build and TypeScript check also passed.

## Additional NASA PDF corpus

Eight additional official PDFs are stored in [`back/data/nasa_references`](back/data/nasa_references/README.md): exercise, sleep accommodations, carbon dioxide, behavioral health, urinary health, venous thrombosis, circadian desynchrony and the health stabilization program. The source catalog pins URLs, verified revisions, file hashes and page counts. They total 138 pages and 848 embedded passages, indexed with the real `all-minilm` model at 384 dimensions. Every document passed a page-aware retrieval check. Three existing document identities were enriched with their PDF; five new references were added. The existing Food and Nutrition index was preserved.

To import the local checked files into another migrated database or reindex after a model change, run `docker compose exec -T api python -m scripts.index_nasa_references` from `back/`. The local `index-report.json` records the actual database IDs and retrieval examples and is ignored by Git. This operation changes public reference knowledge only; it does not create diagnoses, change alert thresholds or modify mission/patient records.

## Individual clinical records

Individual health occurrences, medication consumption, factual health reports and medically reviewed NASA assessments are documented in [`CLINICAL_RECORDS.md`](CLINICAL_RECORDS.md). They reuse health authorization and the NASA RAG corpus. Clinical occurrences remain separate from operational mission occurrences. The NASA source catalog now includes 12 PDFs and 583 pages; all catalog entries were successfully indexed and passed page-aware retrieval after dense-chunk handling was added.
