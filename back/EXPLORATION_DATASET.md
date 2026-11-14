# Exploration dataset

Database: `nasa_front_validation_20261111`. Scenario date: 2026-11-14T06:00:00+00:00.

All operational records are synthetic, in English, and describe fictional people and vehicles. They are not actual flight telemetry, medical records, hardware specifications, or operational thresholds. Public reference passages were reimported from the existing English knowledge bundle.

## Scenario

Asteria 01 is on mission day 21 of a lunar reconnaissance expedition; Horizon 02 launches in 45 days; Asteria Pathfinder records a completed 14-day checkout. Four crew members and six assigned support specialists participate in each mission. A separate global administrator manages access.

Health and mental health series cover 20 completed days of the active expedition and 14 days of the historical mission. Higher workload days correspond to shorter sleep and higher reported fatigue. One additional interrupted sleep report has a documented follow-up. Meals total approximately 2,600 kcal and 2,500 ml water per crew member per recorded day; nutrient values are estimates. Stock entries reconcile exactly against initial allocations and consumption.

The particle event is synthetic and explicitly labeled in catalog, notes, identifier and raw metadata. Radiation dose records are synthetic organ-dose scenario estimates, not derived from proton flux or a clinical risk model. No DONKI sync is claimed. No clinical radiation limits are invented.

## Table analysis

| Table | Previous records | New records |
| --- | ---: | ---: |
| access_audit_events | 0 | 1 |
| active_ingredients | 160 | 8 |
| alembic_version | 1 | 1 |
| astronaut_exams | 16 | 84 |
| crew_activities | 0 | 12 |
| crew_member_allergies | 0 | 1 |
| exam_definitions | 29 | 7 |
| exam_result_reviews | 8 | 67 |
| exam_results | 11 | 73 |
| exam_types | 15 | 7 |
| food_products | 1 | 5 |
| food_stock_movements | 0 | 695 |
| health_alert_events | 15 | 1 |
| health_alert_observations | 10 | 1 |
| health_alert_settings | 0 | 3 |
| health_alerts | 3 | 1 |
| health_notifications | 2 | 1 |
| health_observations | 1497 | 1633 |
| knowledge_documents | 7 | 7 |
| knowledge_passages | 11 | 11 |
| meal_log_items | 0 | 680 |
| meal_logs | 0 | 680 |
| medicine_active_ingredients | 179 | 8 |
| medicines | 161 | 8 |
| mental_health_audit_events | 0 | 1 |
| mental_health_check_ins | 0 | 136 |
| mission_exam_requirements | 16 | 21 |
| mission_food_lots | 0 | 15 |
| mission_members | 30 | 30 |
| missions | 10 | 3 |
| nursing_records | 0 | 8 |
| nutrition_plans | 0 | 8 |
| proton_flux_readings | 0 | 96 |
| psychology_contact_requests | 0 | 1 |
| psychology_follow_ups | 0 | 1 |
| radiation_dose_records | 0 | 80 |
| radiation_exposure_limits | 16 | 0 |
| radiation_follow_ups | 0 | 4 |
| revoked_tokens | 8 | 0 |
| space_weather_event_links | 0 | 1 |
| space_weather_events | 0 | 2 |
| space_weather_sync_runs | 0 | 0 |
| spacecraft | 1 | 2 |
| spacecraft_modules | 0 | 6 |
| users | 32 | 11 |

Migration version metadata was retained. Revoked tokens are empty because the new accounts have no logout history. Database sequences were not reset, so tokens for deleted users cannot resolve to newly created users. External synchronization history and radiation limit tables remain empty for the reasons above.

## Validation and access

The generator first passed a complete transaction with rollback, including database constraints, crew counts, password verification and ledger balances, before applying the replacement in one transaction.

Post-apply checks passed: 15 API read checks and six role logins.

Run `python -m scripts.verify_exploration` inside the configured API container to check login and API response serialization for administrative, astronaut and clinical roles.

Local credentials: `back/backups/exploration-access.json` (mode 600). Administrator: `admin@salus.example`; astronaut: `commander@salus.example`. All scenario accounts use the generated password in that file. Backups and credentials are excluded from Git.

Backup: `back/backups/before_exploration_reset_20261114.dump` (PostgreSQL custom format; archive directory checked with pg_restore). Raw before/after inventory: `back/backups/exploration-report.json`.

## Public scenario references

- https://www.nasa.gov/hrp/about-hrp/
- https://www.nasa.gov/reference/crew-systems/
- https://www.nasa.gov/reference/fundamentals-of-human-health/

These references inform scenario themes only. All mission-specific numbers are simulation assumptions.
