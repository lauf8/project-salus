# Predictive Intelligence — Project Salus

Predictive Intelligence is an analysis layer over the existing health, mission, nutrition, mental health, clinical record, spacecraft and knowledge modules. It does not duplicate those modules and does not change how they record data. It produces preventive attention indicators for human review. It is not a diagnostic system.

## Phase 1 audit: existing structures used

| Area | Existing tables | Use in this module |
| --- | --- | --- |
| Vital signs and self-reports | `health_observations` | Resting heart rate (`heart_rate` with `activity = 'rest'`), blood pressure, respiratory rate, SpO₂, temperature, glucose, sleep duration and quality, fatigue, mood. `collected_at`, `recorded_at`, unit, source, activity and signal quality are kept. Readings with `signal_quality = 'poor'` are excluded. Preflight references (`is_preflight_reference`) become the preferred individual baseline. |
| Symptoms | `health_observations.symptoms_status` | Context for the blood pressure + symptoms candidate signal. Unknown status stays unknown. |
| Clinical alerts | `health_alerts` | Read-only context. Active alerts are shown as evidence and act as contraindications for preventive monitoring actions. Predictions never change, lower or close clinical alerts. |
| Clinical records | `health_occurrences`, `medication_uses` | Context counts only. No diagnosis classifier is built from them. |
| Mental health | `mental_health_check_ins`, `psychology_contact_requests` | Stress, happiness, satisfaction, energy, isolation, workload, crew connection. A pending psychology request blocks a duplicate referral suggestion. |
| Nutrition | `meal_logs`, `meal_log_items.nutrients`, `nutrition_plans` | Daily energy and protein intake. A day counts only after it closes. The nutritionist plan energy target is the specialist-approved threshold. |
| Food supply | `mission_risk_plans`, `mission_food_lots`, `food_stock_movements` | Reuses `MissionRiskService.calculate` (`food-fefo-v1`) for depletion, plus lot expiration. |
| Missions and crew | `missions`, `mission_members` | Subject scoping, authorization, mission status and duration. |
| Occurrences | `mission_occurrences` | Recurrence of confirmed occurrences per mission and per spacecraft. |
| Spacecraft | `spacecraft`, `spacecraft_modules` | Identity, modules, usage history across missions. |
| Knowledge | `knowledge_documents`, `knowledge_passages` | Retrieval through the existing `MissionRagService.search` and Ollama adapter. |
| Audit | `access_audit_events` | Manual analyses, feedback, outcomes and model lifecycle changes. |
| Alerts/notifications | `health_alerts`, `mission_risk_alerts`, `health_notifications` | Not written by this module. Preventive suggestions live in `recommendation_events`, deduplicated per subject and action. |

### Gaps found (no data in the system)

- Body weight, body composition, muscle and lean mass, body fat, bone mineral density and strength: no longitudinal tables. Musculoskeletal analysis always returns `insufficient_data` with these sources listed.
- Laboratory exams exist only as preflight `exam_results.structured_values` with free-form fields. They are not used as time series.
- Mission medicine inventory and dispensing ledger: not stored. Medicine shortage returns `insufficient_data`.
- Spacecraft telemetry, failures and maintenance history: not stored. Technical failure prediction returns `insufficient_data`. Only recurrence of confirmed mission occurrences is reported.
- Operational workload: only the self-reported `workload_level` from mental health check-ins.
- Labeled clinical outcomes: none. Supervised models are limited to an outcome observable in existing data (see below).

## Architecture

```
Existing tables ──> data_collection.py (time-filtered records) ──> features.py (temporal features, quality)
     ──> rules.py (rule signals, anomalies, plan targets, insufficient data)
     ──> health_risk.py / mission_risk.py (HealthRiskPredictionService, MissionRiskPredictionService, SpacecraftRiskPredictionService)
     ──> training.py (offline training, validation, inference of active models)
     ──> recommendations.py (RecommendationEngine: catalog, eligibility, contraindications, ranking)
     ──> knowledge.py (RAG retrieval, applicability check, validated Ollama explanation)
     ──> predictive_service.py (authorization, idempotent runs, persistence, feedback, model lifecycle)
     ──> routers/predictive.py (API) ──> front/src/PredictiveIntelligence.jsx (dashboard)
scripts/predictive_worker.py (scheduled and new-data analysis, retries, evidence, model monitoring)
scripts/train_prediction_models.py (offline training; never activates)
```

Backend code: `back/app/services/predictive/`, `back/app/services/predictive_service.py`, `back/app/models/predictive.py`, `back/app/routers/predictive.py`, `back/app/schemas/predictive.py`.
Configuration: `back/app/config/predictive_rules.json` and `back/app/config/recommendation_catalog.json` (both versioned in Git).

## Feature engineering

For each series and analysis time `as_of`:

- Means over 24 h, 7 days and 30 days; standard deviation, minimum and maximum over 30 days.
- Least-squares slope per day over 14 days; percentage change of the 7-day mean versus the previous 7 days.
- Individual baseline: preflight references when at least 3 exist, otherwise the individual history between 60 and 14 days before `as_of` with at least 5 points. Without one, no deviation is computed.
- Difference and z-score of the 7-day mean against the baseline, frequency of step changes larger than one baseline standard deviation, robust z (median/MAD) of the latest reading, hours since the last measurement.
- Quality per series: `missing`, `sparse`, `no_baseline`, `stale`, `sufficient`; overall missing and usable ratios.

Temporal integrity: a record enters a feature only when both its event time and its `recorded_at` are at or before `as_of`. Meal days enter after the day closes. Mental check-ins enter after their last update. Missing data stays `null` and is never replaced by a normal value.

Known leakage limits: meal deletion and item deactivation, and mental check-in edits, are mutable. A later edit removes the older version from historical replays. The ledger-based food projection has no such limit.

## Rules and anomalies (`predictive-rules-v1`)

Thresholds are statistical, not clinical: a sustained deviation is a 7-day mean at least 2 baseline standard deviations from the individual baseline with at least 3 points in the window. An anomaly is a latest reading with robust z ≥ 3.5. Nutrition shortfall uses the active nutritionist plan target (10% tolerance, at least 4 logged days).

| Domain | Risk types |
| --- | --- |
| Cardiovascular | `cardiovascular_resting_heart_rate_shift`, `cardiovascular_blood_pressure_shift`, `cardiovascular_heart_rate_with_sleep_change` (combined), `cardiovascular_pressure_with_symptoms` (combined) |
| Sleep and fatigue | `sleep_deficit`, `sleep_fatigue_combined` (combined), `fatigue_increase` |
| Psychological attention | `psychological_stress_persistent`, `psychological_mood_with_stress` (combined), `psychological_wellbeing_decline` |
| Nutrition | `nutrition_energy_intake_low`, `nutrition_protein_intake_low`, `nutrition_below_plan_target` |
| Anomalies | `anomaly_<indicator>` for vital signs and glucose |
| Mission | `food_shortage`, `food_expiration`, `collective_fatigue`, `collective_wellbeing_decline`, `collective_workload`, `recurring_occurrence` |
| Spacecraft | `spacecraft_recurring_occurrence` |
| Insufficient data | `<domain>_insufficient_data`, `medicine_supply_insufficient_data`, `food_supply_insufficient_data`, `technical_failure_insufficient_data`, `collective_health_insufficient_data` |

Combined signals are marked `candidate_signal`. They are correlations for review, not causal findings. Risk levels (`low`, `moderate`, `high`) describe deviation strength or concurrency, not clinical severity. A score always states its meaning. Only `ml` predictions may carry `calibrated_probability`, and a database constraint enforces this.

Collective signals require individual analyses for at least 2 astronauts and at least half of the analyzed crew. They expose counts only.

## Machine learning

- Outcome: `elevated_fatigue_24h`, defined as at least one fatigue self-report in the next 24 hours at or above the individual baseline mean plus 2 standard deviations, with the baseline computed only from data available at prediction time. This outcome is observable in existing data. System alerts are never used as labels.
- Samples: one per astronaut-day at 12:00 UTC. Features from sleep, fatigue, resting heart rate, stress and sleep quality. Samples with more than 40% missing inputs are skipped.
- Split: temporal; the most recent 30% of prediction times form the test set.
- Candidates: calibrated logistic regression and calibrated random forest (scikit-learn), with a median imputer plus missing-value indicators.
- Baselines: training prevalence and persistence (elevated fatigue in the last 24 hours).
- Metrics: precision, recall, F1, PR-AUC, Brier score, expected calibration error with a reliability table, false negatives and false positives.
- Gate: at least 200 training samples, 20 training positives and 10 test positives; PR-AUC at least 0.05 above the best baseline; Brier score below the best baseline; calibration error ≤ 0.10; recall ≥ 0.5. Failing models are stored as `rejected`.
- Lifecycle: `candidate` → `approved` → `active` → `retired`. Only a global administrator can approve or activate, and activation requires a passed gate. Activating a version retires the current one; activating a retired version is the rollback. Every run stores the model versions it used. Artifacts are stored with SHA-256 and verified before loading.
- Monitoring: the worker scores matured predictions of active models and flags `degraded` when the Brier score exceeds the validation value by 0.05 or calibration error exceeds 0.10. It never retires a model automatically.

Current metrics: no model is trained or active on real records. On the synthetic cohort used in tests (6 astronauts × 120 days, seed 11), the selected logistic regression reached PR-AUC 0.62 against 0.35 for persistence, Brier 0.050 against 0.075, calibration error 0.039, recall 0.50 and precision 0.60 on 186 test samples. These numbers only verify the pipeline. They are not clinical validation.

Train and inspect from `back/`:

```bash
docker compose exec -T api python -m scripts.train_prediction_models --dry-run
docker compose exec -T api python -m scripts.train_prediction_models
```

## Recommendations

`recommendation_catalog.json` holds the approved, versioned catalog (`recommendation-catalog-v1`) of non-prescriptive actions: flight surgeon review, repeated vital sign measurements, rest-period review, workload review, fatigue monitoring, psychologist contact, crew cohesion review, nutritionist intake review, food inventory verification and recurring occurrence review. Each entry has eligible risk types, responsible roles, eligibility rules, contraindications, priority, evidence quality, feasibility, NASA references and a retrieval query. A new version of an entry retires the older approved version when the catalog syncs. Syncing happens before every analysis and in the worker.

Ranking weights: urgency 0.25, relevance 0.20, evidence quality 0.15, context fit 0.10, feasibility 0.10, historical outcomes 0.10 (Laplace-smoothed improvement rate from recorded outcomes) and catalog priority 0.10. Contraindicated and ineligible actions are removed before ranking and listed in the prediction evidence. A high score never overrides a contraindication. Pending suggestions that a newer analysis no longer supports become `superseded`. Only one open suggestion exists per subject and action.

Feedback flow: `pending → accepted | rejected`, `accepted → executed | rejected`. `executed` requires a description of the action. Outcomes (indicator, before/after values, observation window, result) can be recorded for accepted or executed suggestions and feed the historical outcome component.

## RAG and Ollama

1. A rule or model identifies a risk.
2. The engine selects catalog actions.
3. `MissionRagService.search` retrieves NASA passages with the action's query.
4. Passages must share at least one topic term with the query to count as applicable.
5. Ollama receives only the risk title and type, kind, level, horizon, factor names and directions, any calibrated probability and the action. Names, identifiers, notes and raw values are not sent.
6. The explanation must match a strict schema, cite only retrieved passage IDs and may not mention probabilities or percentages unless a calibrated probability exists. Otherwise a deterministic summary is kept.

States: `documented`, `no_documentary_evidence`, `rag_unavailable`. The worker fills pending evidence; `POST /v1/recommendations/{id}/evidence` refreshes it on demand. Ollama failure never removes predictions or suggestions.

## Data model (migration `3f1a2b4c5d60_predictive_intelligence.py`)

`prediction_models`, `feature_snapshots`, `prediction_runs`, `risk_predictions`, `recommendation_actions`, `recommendation_events`, `recommendation_feedback`, `recommendation_outcomes`. The migration only creates tables, so existing rows are untouched. Constraints cover subject types, statuses, risk levels, probability range and kind, one active model per name, one open suggestion per subject and action, and unique idempotency keys.

## API (`/v1` prefix, like the rest of the backend)

| Method | Path | Access |
| --- | --- | --- |
| GET | `/predictions/dashboard` | Any user; content filtered by profile |
| GET | `/predictions/astronauts/{id}?mission_id=` | The astronaut; mission flight surgeon or nurse (clinical areas); psychologist (psychological area); nutritionist (nutrition area) |
| POST | `/predictions/astronauts/{id}/analyze?mission_id=` | Same as above; rate-limited |
| GET | `/predictions/missions/{id}` | Mission members and global administrators |
| POST | `/predictions/missions/{id}/analyze` | Mission administrator, flight surgeon or nutritionist; rate-limited |
| GET | `/predictions/spacecraft/{id}` | Any user |
| GET | `/recommendations?status=&mission_id=` | Filtered to visible subjects and areas |
| GET | `/recommendations/{id}` | Visible subjects only |
| POST | `/recommendations/{id}/feedback` | Mission member whose role is responsible for the action |
| POST | `/recommendations/{id}/outcomes` | Same as feedback |
| POST | `/recommendations/{id}/evidence` | Visible subjects only |
| GET | `/prediction-models`, `/prediction-models/{id}/metrics` | Any user; artifacts are never returned |
| POST | `/prediction-models/{id}/approve`, `/activate`, `/retire` | Global administrator |

Global administrators do not get astronaut health predictions through this module, matching existing health-record rules. Mental health predictions follow the mental health rules: the astronaut and the mission psychologist only.

## Monitoring, idempotency and failures

- `predictive-worker` (Compose) runs `scripts.predictive_worker --watch`. For every started, unfinished mission it analyzes each astronaut, then the mission, then its spacecraft; fills pending evidence; and monitors active models.
- Idempotency key: subject, mission, input fingerprint, active rule/catalog/model versions, engine version and a schedule bucket (`PREDICTION_SCHEDULE_HOURS`). Unchanged inputs inside a bucket reuse the existing run. Changed inputs create a run with trigger `new_data`.
- Failures are stored with status `failed` and the error. The same key is retried up to `PREDICTION_MAX_ATTEMPTS`. Measurement registration never calls the predictive engine, so it cannot be blocked by it.
- Manual analyses are limited per subject by `PREDICTION_MANUAL_COOLDOWN_SECONDS` (HTTP 429 with `Retry-After`).
- When engine logic changes, increase `ENGINE_VERSION` in `app/services/predictive/config.py` so new analyses are not deduplicated against runs from the previous logic.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PREDICTION_MANUAL_COOLDOWN_SECONDS` | `300` | Minimum interval between manual analyses of a subject |
| `PREDICTION_SCHEDULE_HOURS` | `6` | Scheduled refresh bucket when inputs are unchanged |
| `PREDICTION_WORKER_INTERVAL_SECONDS` | `300` | Worker loop interval |
| `PREDICTION_MAX_ATTEMPTS` | `3` | Retries for a failed run |

Ollama variables are shared with mission risks (`MISSION_RISKS.md`).

## Frontend

Sidebar item **Predictive Intelligence** (`front/src/PredictiveIntelligence.jsx`, `predictive.js`, `predictive.css`):

- Dashboard: monitored astronauts and missions, risk levels, prediction kinds, areas, pending suggestions, analyses per day, astronaut and mission tables, top-ranked pending suggestions.
- Astronaut: potential problems, indicators with baseline, deviation, trend and data quality, a 30-day chart with the baseline line, suggestions with sources and feedback, action and outcome history, run history.
- Mission: operational risks, supply table with days of stock and range, collective trends, incident history, prioritized suggestions, run history.
- Spacecraft: technical risk state and usage history.
- Models: status, validation summary, approval, activation, rollback and retirement for global administrators.

Each card shows its kind (rule-based, statistical anomaly, machine learning, insufficient information). Probabilities appear only for validated ML predictions.

## Verification

From `back/` with PostgreSQL:

```bash
docker compose exec -T api python -m pytest -q tests/test_predictive_engine.py
docker compose exec -T -e PREDICTIVE_POSTGRES_TESTS=1 api python -m pytest -q tests/test_predictive_postgres.py
docker compose exec -T api python -m scripts.predictive_worker
```

From `front/`:

```bash
npm test
npm run typecheck
npm run build
npm run test:predictive:e2e
```

Results recorded for this change are in the pull request or commit description. Synthetic test data in `back/tests/predictive_synthetic.py` is never clinical or operational validation.

## Limitations and features that need more data

- Musculoskeletal risk needs weight, body composition, lean mass, bone density and strength series.
- Laboratory trends need repeated in-mission structured results.
- Medicine shortage needs a mission medicine inventory and dispensing ledger.
- Equipment failure prediction needs telemetry, failure and maintenance records with validated failure definitions.
- Workload risk would improve with scheduled task or duty-period data.
- Supervised models need real longitudinal data that meets the gate. Until then only rules and anomalies are active.
- Disease-specific classifiers are intentionally absent: there are no labeled outcomes, clinical outcome definitions or validation.
