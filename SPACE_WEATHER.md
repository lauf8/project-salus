# Space weather (NASA DONKI)

The module imports solar flares (FLR), coronal mass ejections (CME) and solar energetic particle events (SEP) from NASA DONKI, stores the links between them and prepares the radiation exposure tables.

The basis is NASA SP-2009-3405, chapter 5 (*Risk of Acute Radiation Syndromes Due to Solar Particle Events*). Flares and CMEs are **precursors**; the SEP is the **exposure** event. The API response gives this role in `health_relevance` (`precursor` or `exposure`). An event in DONKI does not mean that a crew member received a relevant dose: the dose depends on the intensity, the spacecraft location, the shielding and the crew member's activity (EVA, IVA or shelter).

## Configuration

Set `NASA_API_KEY` in `.env`. The free key is available at https://api.nasa.gov. Without it, `DEMO_KEY` is used, which has a low hourly and daily request limit. Optional variables: `DONKI_BASE_URL` and `DONKI_TIMEOUT_SECONDS`.

Apply migrations `f9a1b2c3d4e5` and `0b7c1d2e3f40`:

```sh
docker compose exec api alembic upgrade head
```

## Tables

| Table | Use |
| --- | --- |
| `space_weather_events` | FLR/CME/SEP event with the DONKI ID (`activity_id`, unique), times, flare class and peak X-ray flux (W/m²), data from the CME analysis marked as most accurate, instruments, version and the original JSON in `raw`. |
| `space_weather_event_links` | `linkedEvents` links. The linked event can be of a type that is not imported (IPS, GST...); the type is extracted from the ID. |
| `space_weather_sync_runs` | Each DONKI request, with counts and errors, including failures. |
| `proton_flux_readings` | Integral proton flux (GOES/NOAA SWPC) per energy channel, in pfu. Source `noaa_swpc` or `simulation`. |
| `crew_activities` | Where each crew member was: `iva`, `eva` or `storm_shelter`. |
| `radiation_exposure_limits` | Limits per organ and period, versioned by profile. |
| `radiation_dose_records` | Dose per crew member, organ and period, with source `dosimeter`, `model_estimate` or `simulation`. |
| `radiation_follow_ups` | 48 h window after an SEP, opened for crew who were on EVA, with the reported symptoms. |
| `radiation_symptom_reports` | Each symptom report in the window, from the form or from a health measurement. |
| `radiation_alerts` | Radiation alerts. They have their own table because `health_alerts` requires a source measurement. |

The migration loads the `nasa-sp-2009-3405-table-5-1` profile, which reproduces Table 5-1 of the book (2009). NASA revised these limits later (NASA-STD-3001); for current values, create a new profile instead of changing the existing one.

## Endpoints

Prefix `/v1/space-weather`.

| Method | Path | Use |
| --- | --- | --- |
| POST | `/sync` | Imports from DONKI. Body: `start_date`, `end_date` (up to 366 days) and `event_types` (default `FLR`, `CME`, `SEP`). Requires a physician assigned as `flight_surgeon` or `mission_admin` in some mission. |
| GET | `/sync-runs` | Latest synchronizations. |
| GET | `/events` | Paginated list. Filters: `event_type`, `start` and `end` (with time zone). |
| GET | `/events/{activity_id}` | Event with links in both directions; linked events that were not imported appear with `stored=false`. |
| GET | `/missions/{mission_id}/events` | Events overlapping the mission period. Requires mission membership. |
| GET | `/exposure-limits` | Dose limits; optional `profile_id` filter. |

Example:

```json
POST /v1/space-weather/sync
{"start_date": "2024-10-01", "end_date": "2024-11-14", "event_types": ["FLR", "CME", "SEP"]}
```

The interval is queried in 30-day windows. Each type is stored in its own transaction: if one type fails, the others continue and the failure is recorded. If all fail, the response is 502. A new synchronization of the same period does not duplicate events; versions revised by DONKI update the fields and replace the links.

## Scheduled synchronization

```sh
docker compose exec api python -m scripts.sync_space_weather --days 7
docker compose exec api python -m scripts.sync_space_weather --start 2024-10-01 --end 2024-11-14 --types SEP
```

The script returns exit code 1 if any type fails.

## Radiation flow

Prefix `/v1/radiation`. Screen: the mission's **Radiation** tab.

1. **Crew activity.** The astronaut (for themself), the flight surgeon or the mission administrator records IVA, EVA or shelter. Activities of the same astronaut cannot overlap and must be within the mission period.
2. **SEP during EVA.** When an SEP is imported from DONKI (API or script), the system looks for EVAs that cover the SEP start. An EVA without an end only counts if it started up to 12 h before. For each crew member found, it opens a follow-up with a 48 h window from the SEP start and creates the `sep_during_eva` alert. An EVA recorded after the import also triggers the check. Manual reprocessing is available at `POST /events/{activity_id}/process`.
3. **Symptoms.** Nausea, vomiting, loss of appetite, fatigue and skin (`nausea`, `vomiting`, `anorexia`, `fatigue`, `skin_erythema`) are part of the symptom list of health measurements. If the measurement falls within an open window, it becomes a follow-up report. Reports can also be made directly in the follow-up.
4. **Proton flux.** `POST /proton-flux/sync` imports the GOES integral flux from NOAA SWPC. The service only publishes the last 7 days, so schedule `python -m scripts.sync_proton_flux`. For past events or demonstrations, `POST /proton-flux/simulate` generates a synthetic ≥10 MeV profile for an SEP.
5. **Doses.** The flight surgeon records measured or estimated doses (`POST /missions/{id}/doses`) or generates simulated doses (`POST /missions/{id}/doses/simulate`). The simulation integrates the ≥10 MeV flux with each crew member's activity and is a **teaching** estimate: 0.02 mGy-Eq/h per pfu to the skin on EVA, shielding of 0.15 in IVA and 0.05 in the shelter, and per-organ factors. It is not dosimetry. `GET /missions/{id}/astronauts/{id}/dose-summary` compares the accumulated dose with the limits profile.

### Alerts

| Rule | When | Severity |
| --- | --- | --- |
| `sep_during_eva` | Crew member on EVA at the SEP start | urgent; critical if the ≥10 MeV peak in the 48 h is ≥ 1000 pfu (S3) |
| `proton_flux_during_eva` | ≥10 MeV flux ≥ 10 pfu (S1) during an EVA | attention (S1), urgent (S2), critical (S3+) |
| `prodromal_vomiting` | Vomiting within the 48 h window | critical |
| `prodromal_symptoms` | Nausea, loss of appetite or fatigue within the window | urgent |
| `skin_reaction` | Skin reaction within the window | urgent |
| `late_symptoms` | Symptoms reported after the window | attention |
| `dose_limit` | Accumulated dose ≥ 50%, 75% or 100% of the limit | attention, urgent, critical |

The thresholds are simulation values. There is one active alert per astronaut and logical rule: a new, more severe finding raises the severity and reopens the alert. Astronauts can acknowledge their own alerts; only the flight surgeon resolves them and closes the follow-up. Radiation alerts do not create notifications in the notification center yet.

### Endpoints

| Method | Path | Use |
| --- | --- | --- |
| GET | `/missions/{id}/timeline` | Events in the period, flare → CME → SEP chains, activities, follow-ups and active alerts (the last two only for the flight surgeon or the astronaut). |
| GET, POST | `/missions/{id}/crew-activities` | Lists and records activities. |
| POST | `/missions/{id}/crew-activities/{activity_id}/end` | Ends an activity. |
| GET, POST | `/missions/{id}/doses` | Lists and records doses. |
| POST | `/missions/{id}/doses/simulate` | Simulated doses from the flux. |
| GET | `/missions/{id}/astronauts/{astronaut_id}/dose-summary` | Accumulated dose × limits. |
| GET | `/missions/{id}/follow-ups[/{follow_up_id}]` | Follow-ups. |
| POST | `/missions/{id}/follow-ups/{follow_up_id}/reports` | Symptom report. |
| POST | `/missions/{id}/follow-ups/{follow_up_id}/close` | Closure by the flight surgeon. |
| GET | `/missions/{id}/alerts` | Alerts (`status`: `active`, `open`, `acknowledged`, `resolved`, `all`). |
| POST | `/missions/{id}/alerts/{alert_id}/acknowledge`, `/resolve` | Acknowledge and resolve. |
| POST | `/events/{activity_id}/process` | Reprocesses an SEP. |
| GET | `/proton-flux` | Readings per channel and period. |
| POST | `/proton-flux/sync`, `/proton-flux/simulate` | NOAA SWPC import and simulation. |

Optional variables: `SWPC_BASE_URL`, `SWPC_GOES_SATELLITE` (`primary` or `secondary`) and `SWPC_TIMEOUT_SECONDS`.

## Demonstration scenario

On a migrated development database, without internet access:

```sh
docker compose exec api python -m scripts.seed_radiation_demo
```

It creates the "Radiation Demo" mission with a fictional flare X2.3 → CME → SEP chain from 10 hours ago, an astronaut's EVA during the SEP (with an open 48 h window), simulated flux and doses, and a symptom report. At the top of the screen, choose Profile **Physician** and User **Dr. Rivera** (flight surgeon), or Profile **Astronaut** and User **Ada Lima**. Then open Missions → Radiation Demo → Radiation tab.

## Verification

```sh
pytest tests/test_space_weather.py tests/test_radiation.py
```

The tests use simulated responses in DONKI format (the 2024-10-26 chain: flare X1.8, CME and SEP) and do not access the internet.
