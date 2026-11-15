# Synthetic history of 50 missions

The `scripts.seed_synthetic_missions` command creates a fictional set for functional validation. It uses the existing models, without a migration. By default, it does not change the public tables of missions, patients or recommendations. The tables are created from the project metadata in a dedicated PostgreSQL schema, with no `search_path` fallback to `public`. The configured public corpus is copied with its PDFs, passages, URLs, revisions, hashes and original dates. No fixture documents or new NASA references are created.

## Data visible in the application

To create the 50 missions in the same `public` schema used by the interface, run from `back/`:

```bash
docker compose exec -T -e SALUS_SYNTHETIC_ENV=development api python -m scripts.seed_synthetic_missions --publish --evaluate --output data/synthetic_missions_public
```

Then refresh the page and select **Mission administrator → Rafael Andrade**. In **Missions**, the 50 history missions go from `Aurora 01` to `Cruzeiro 05`; this user is assigned to all of them. For health and medical records, select **Physician → Helena Monteiro**. Permissions of earlier accounts are preserved.

The `--publish` option adds the records to the application database, keeps pre-existing missions, rejects name and account conflicts and validates the distribution only for the 50 seeded missions. Repeated runs with the same parameters reuse the set. Public artifacts are in `back/data/synthetic_missions_public/` and use the real application IDs; artifacts of the isolated schema have independent IDs. The overall table counts in the public report include pre-existing records, while the mission distribution is limited to the seed. The existing public corpus is reused directly.

The texts that this generator writes into records (names, notes and summaries) are matched exactly on repeated runs and by the export preparation, so they keep the wording they were created with.

## Isolated run

From `back/`, with the application and PostgreSQL migrated:

```bash
docker compose exec -T -e SALUS_SYNTHETIC_ENV=development api python -m scripts.seed_synthetic_missions --evaluate --evidence --output data/synthetic_missions
```

Only generate or check the data:

```bash
docker compose exec -T -e SALUS_SYNTHETIC_ENV=test api python -m scripts.seed_synthetic_missions --output data/synthetic_missions
```

Repeating the first command runs or checks the recommendations and operational alerts through the real services. `--evidence` uses `PredictiveKnowledgeService`, `MissionRagService` and the configured Ollama. A corpus unavailable at the cutoff or an unavailable Ollama keeps the deterministic fallback. Without this option, evidence stays pending, as in the normal flow before the worker runs.

Fixed parameters: `--seed 50`, `--reference 2026-11-15T12:00:00+00:00`, `--schema salus_synthetic_50`. Another seed or date requires another `salus_synthetic_*` schema; divergent parameters are rejected. The reference requires a time zone and is normalized to UTC. The `SALUS_SYNTHETIC_ENV` variable must be `development` or `test`; explicit production markers in `APP_ENV`, `ENVIRONMENT` or `ENV` block the run. This protection complements the separation of development credentials; on its own it does not identify a misconfigured production database.

A transactional lock serializes runs in the same namespace. One outer transaction covers generation, checks and evaluations; internal service commits use savepoints. Failures roll back the set's records, allowing a new attempt. The empty schema can remain. There is no cleanup command. Sequence IDs can have gaps after a failure. Accounts use the reserved domain `example.test` and a blocked password (`!`). Nothing is sent externally; notifications are synthetic internal records.

The files `back/data/synthetic_missions/manifest.json` and `report.json` stay outside the engine inputs. The first contains the scenario, IDs, cutoff, count per series, IDs of available observations, expectation, partition and later outcomes; the second contains totals, recommendations and a per-case comparison. Names and observations consumed by the engine do not encode the scenario or the expectation.

## Inventory and coverage

Models, input schemas, migrations, services, predictive routes, existing seeds, PostgreSQL tests and frontend modules were examined. The real constraints use `planned`, `in_progress` and `completed` missions; the fleet allows only one unfinished mission per spacecraft. There is no individual boarding date: the membership is `mission_members`, with dates bounded by the mission.

| Area/frontend | Generated data / capability |
| --- | --- |
| Missions and operations | 35 completed, 10 in progress, 5 planned; 2–4 astronauts; periods of 7–180 days and extension of in-progress missions; a spacecraft is reused only in separate historical periods, exclusive fleet for open missions, some missions without a spacecraft; varied habitable modules |
| Profiles and permissions | Astronauts exclusive to each mission; physician, administrator, psychologist, nutritionist, nurse and observer assigned with real flags; no global clinical access is granted |
| Exams and medical records | Preflight requirement, scheduling, result and accepted review; fictional pre-existing conditions in part of the crew; active ingredient allergies; recovered clinical occurrences and medication uses after the cutoff |
| Health | Resting heart rate, blood pressure, respiration, SpO₂, temperature, glucose, sleep in minutes, sleep quality, fatigue, mood, attention and AVPU; own preflight references; individual differences, daily variation and irregular series with late recording |
| Mental health | Check-ins with real fields and weekly follow-ups; the follow-up text is not a prediction input; the analysis uses only the available ratings |
| Nutrition | Fictional composite product, lots, expiration, three daily meals, macros, nutrition plan, immutable receipt/consumption movements and reconciled balance |
| Operational risks | Versioned food planning, real FEFO projection, expiration, alerts and internal notifications when a shortage is projected; confirmed occurrences in completed missions |
| Predictive Intelligence | Individual, mission and spacecraft analyses; real snapshots, predictions and recommendation events; existing catalog, ranking and contraindications |
| Body composition/physical assessment | There are no longitudinal tables for weight, lean mass, fat, strength or bone density; scenario explicitly without assessment |
| Telemetry/maintenance | There are no series or maintenance orders; an occurrence of category `spacecraft` does not allow early failure prediction; scenario explicitly without assessment |
| Radiation | The module exists but is not used by these predictive rules; the seed does not simulate external space weather ingestion |

There is no dedicated field for the dynamic mission phase; phases are represented in occurrences and by the existing dates and states. Structured exams do not represent longitudinal clinical series. There is no medication stock or universal supervised clinical outcome. Clinical records and operational occurrences stay separate.

## Scenarios and expectations

Each of the ten scenarios is repeated five times. The last five cases have only preflight data at the cutoff, keeping the 5 requested planned states.

- Stable: no unjustified positive signals at the cutoff.
- Isolated: a spike outside the final seven-day window and a return to baseline; no sustained deviation at the cutoff. This does not require the rule to stop flagging the anomaly at the time of the spike.
- Progressive: rising resting heart rate; `cardiovascular_resting_heart_rate_shift` and a medical review are expected.
- Sleep/fatigue: less sleep with increasing fatigue; `sleep_fatigue_combined` and a rest review are expected.
- Mental report: rising stress and lower mood, with a later follow-up; psychological support is expected when there is a sufficient baseline.
- Body composition: a schema gap; no assessed trend is invented.
- Food: upcoming expiration, with a projected shortage in part of the periods; an inventory check is expected.
- Technical incident: a later confirmed occurrence; the lack of telemetry prevents assessing early failure detection.
- Irregular: preflight references present and long gaps during flight; the answer can be insufficient data, without filling gaps with normal values.
- Pairs: similar heart rate signals, with a later clinical occurrence in one group and no recorded occurrence in the other; they allow inspecting divergences between preventive attention and the recorded outcome.

Expectations are fixed by the case design, not derived from the recommender output. The main matrix compares the rule contract with the signals produced; `expected_action_found` checks the recommendation separately. A preventive alert followed by no diagnosis is not automatically a clinical false positive. The manifest distinguishes later confirmation, absence of a recorded event and incomplete follow-up. No diagnostic capability is attributed to the rules.

## Time cutoff

Each completed mission is evaluated two days before it ends; in-progress and planned missions use the reference. Evaluations run in chronological order, with a controlled clock at the boundary of services that already use `utc_now`, without changing the database clock. The real analyses persist their runs, snapshots and recommendations. There is no training, threshold tuning or model activation. Missions 1–30 are development and 31–50 are evaluation; the partition is by mission and keeps the time order.

Health collection requires collection and recording before the cutoff. Meal days only count after they close; check-ins only count after their update. Mission aggregation excludes individual runs after the cutoff. Occurrences of all missions and spacecraft require the event, record and confirmation to be available. Stock for expiration is rebuilt from the ledger at the cutoff; future receipts are excluded. Mission condition and duration are rebuilt from the dates. The ranking excludes recommendation outcomes assessed after the cutoff. Documents used by `--evidence` must have been imported and indexed by the cutoff; the corpus is not backdated.

Existing historical limitations: editing meals or check-ins removes old versions; configuration and the action catalog do not have complete temporal versioning of approval; spacecraft and module metadata have no availability date. The set does not edit these data after creation and does not use supervised models. A corpus indexed after a cutoff is unavailable at that cutoff, even if the PDF is old. No historical reproduction of old clinical policies is claimed. Generation uses direct historical insertion through the models, like the existing seeds, to preserve dates; recommendations and operational alerts go through the real services. Clinical threshold alerts are not recalculated by this seed, which avoids mixing the predictive test with that separate protocol.

In isolated mode, the data stays in the dedicated schema and does not automatically appear in the web instance that uses `public`. To use it in the existing interface, use `--publish`, as described above. To inspect the interface, use a separate development instance pointing its `search_path` only at the synthetic schema. Do not change the `search_path` of the shared database user. The command and tests cover the real backend; there is no new browser test.

## Verification

```bash
docker compose exec -T -e PREDICTIVE_POSTGRES_TESTS=1 api python -m pytest -q tests/test_synthetic_missions.py tests/test_predictive_engine.py tests/test_predictive_postgres.py
git diff --check
```

PostgreSQL checks the foreign keys and constraints. The command checks the distribution and reconciles each lot with its movements. The additional tests check chronology, no overlap in the historical spacecraft, states at the cutoff and exclusion of future analyses, events and confirmations. Run the complete command again to check idempotence of the seed records and recommendations.

## Local run result

The real generation in PostgreSQL confirmed **50 missions (35/10/5)**, 155 users, 449 memberships, 102,132 health observations, 7,319 check-ins, 997 weekly follow-ups, 21,672 meals and 21,722 stock movements. 51 clinical histories/occurrences and 35 operational occurrences were recorded. The 50 lots had their balances reconciled.

In the functional comparison with the rules: **23 true positives, 14 true negatives, 0 false positives, 0 false negatives and 13 cases without assessment**. The cases without assessment are the scenarios without a body composition or telemetry schema and the preflight-only cases. All expected actions in the assessable cases were found, including open suggestions reused through idempotence. These counts do not measure clinical effectiveness or the ability to predict diagnoses.

Repeating with the final implementation preserved the source totals, 291 accumulated runs, 147 recommendations and the notifications, without creating new records. The database contains 147 recommendations, 2 operational alerts and 2 internal notifications. The documentary assessment of the manifest cases found 11 documented recommendations and 37 without evidence available at the cutoff; 99 suggestions for other crew members, missions or spacecraft stayed pending enrichment, because `--evidence` assesses the subjects chosen in the manifest. The copied corpus has 16 documents. No source was backdated.

The Predictive Intelligence, risks and additional test suite passed **57 tests, with 1 optional Ollama test skipped**. The seed assessment with `--evidence` used the configured Ollama, independently of that optional test. After the fix that preserves historical balance units, the targeted set passed 19 tests again. `git diff --check` and compilation of the new Python modules passed.

Implementation files: `back/scripts/seed_synthetic_missions.py`; historical collection and state in `predictive/data_collection.py`; stock, aggregation and recurrence in `predictive/mission_risk.py`; cutoff of results in the ranking in `predictive/recommendations.py` and `predictive_service.py`; documentary lookup in `mission_rag.py` and `predictive/knowledge.py`; tests `test_synthetic_missions.py` and the ledger adjustment in `test_predictive_postgres.py`; this document and the artifacts `back/data/synthetic_missions/manifest.json` and `report.json`.

## Publication in the interface database

The run with `--publish` wrote the 50 missions to the `public` schema, IDs **216–265**, and kept the **6 earlier missions**. The real API `GET /v1/missions?per_page=100`, with the `Equipe Sintética mission_admin` user, answered HTTP 200 with exactly 50 visible missions, from `Salus Synthetic 001` to `Salus Synthetic 050`, split into 35 completed, 10 in progress and 5 planned. The assessment in that database kept 23 true positives, 14 true negatives and 13 cases without assessment, with no false positives or negatives in the rule contract. The new artifacts are in `back/data/synthetic_missions_public/`.

The fix adds `--publish` to the generator, limits the distribution and balance checks to the synthetic IDs and checks that the pre-existing missions are still present. The coexistence test with earlier records passed with the other generator tests: **6 tests passed**. The isolated option remains available for tests without inserting into the interface.

## Display names and export

The export preparation, the plausible fictional names, the external traceability and the full database restore are documented in [DATABASE_EXPORT.md](DATABASE_EXPORT.md). After that preparation, `--publish` recognizes the same IDs through the external `presentation.json` record, keeping idempotence even with the new names. The old names cited in the historical results above correspond to the run before the preparation.
