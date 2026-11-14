# Account profiles and mission responsibilities

Project Salus supports eight account profiles. Profiles can be combined. A mission membership retains one responsibility per user and mission; the same user can have a different responsibility in another mission.

| Account profile | Mission responsibility | Scope |
| --- | --- | --- |
| Global administrator | No membership required for administration | All mission operations, account profiles, account activation, operational catalogs and access audit metadata. Does not automatically grant access to individual clinical, nursing, dietary or psychological records. |
| Mission administrator | `mission_admin` | Manage assigned mission, participants, spacecraft, dates and inventory. Medical requirements and alert thresholds still require a physician profile. |
| Astronaut | `astronaut` | Own health observations, meal journal, examinations, mental health check-ins, shared follow-ups, nutrition plans and nursing records. |
| Physician | `flight_surgeon` | Authorized mission health monitoring, medical examination results and reviews, allergies and alerts. Can consult nutrition plans and nursing records. Cannot read the psychological diary or private psychology sessions. |
| Psychologist | `psychologist` | Assigned mission mental health journals, contact requests and psychological follow-ups. Only the session author can correct it. |
| Nutritionist | `nutritionist` | Read assigned astronauts' food and hydration consumption, manage food product nutrition information, and record or correct their own nutrition plans. Nutrition context contains registered ingredient allergies and the latest mission glucose reading, without observation notes. Cannot change the astronaut's meal journal. |
| Nurse | `nurse` | Record health observations, consult and acknowledge alerts, register nursing observations, care and sample collection. Cannot accept medical examination reviews, set physician-only preflight reference values, resolve medical alerts, prescribe medication or read psychology journals. |
| Observer | `observer` | Read assigned mission operational information, participant counts and crew. No individual health, dietary, nursing or psychological records and no mission mutations. |

A professional account profile alone does not grant access to astronaut records. The corresponding mission membership is required. Global administrator access is deliberately restricted to administrative operations; a clinical role requires its own explicit mission assignment. Removing a professional membership revokes its access. Astronaut memberships with care history remain protected from deletion or conversion.

## Registration and administration

Public registration exposes the seven non-global account profiles and rejects `is_global_admin` and `is_active` input. Mission administrators can create missions. Existing physician accounts retain the ability to create missions for compatibility. Creating a mission assigns its creator as mission administrator. Existing mission administrators receive the account-level mission administrator flag during migration.

Global administrators use **User administration** to grant or remove profiles and activate or disable accounts. Profile removal is blocked while an incompatible mission responsibility remains assigned. The last active global administrator cannot be disabled or demoted. Deactivated accounts cannot sign in and existing tokens no longer authorize API access.

The initial global administrator must be assigned to an existing active account from a trusted backend shell:

```sh
python -m scripts.bootstrap_global_admin --email ACCOUNT_EMAIL
```

The command refuses to run once an active global administrator exists. Subsequent grants go through the protected administration API and screen. No account is automatically promoted by registration or migration.

## Screens

- **Sign up**: selectable public profiles, including nutritionist, nurse, observer and mission administrator.
- **User directory**: combined profile labels.
- **User administration**: global administrators only; account profiles, activation and paginated access audit.
- **Missions → Operations**: operational overview, including observer access.
- **Missions → Crew**: mission role assignment, controlled by mission/global administration.
- **Missions → Nutrition plans**: nutritionist workspace; astronaut and physician consultation.
- **Missions → Nursing care**: nurse workspace; astronaut and physician consultation.
- **Health monitoring**: astronaut, physician and nurse views; physician-only actions remain protected by the API.
- **Mental health**: remains restricted to the astronaut and assigned psychologists.

Forms retain input after a failed save. Administrative, clinical and psychological permissions are enforced by the backend even if a client calls the API directly.

## API additions

- `GET /v1/users/me`
- `PUT /v1/users/{user_id}/profiles`: complete profile and active-state replacement; global administrators only.
- `GET /v1/users/access-audit`: paginated metadata; global administrators only.
- `GET /v1/missions/{mission_id}/operations`
- `GET|POST /v1/missions/{mission_id}/astronauts/{member_id}/nutrition-plans`
- `PUT /v1/missions/{mission_id}/astronauts/{member_id}/nutrition-plans/{record_id}`
- `GET /v1/missions/{mission_id}/astronauts/{member_id}/nutrition-context`
- `GET|POST /v1/missions/{mission_id}/astronauts/{member_id}/nursing-records`
- `PUT /v1/missions/{mission_id}/astronauts/{member_id}/nursing-records/{record_id}`

Nutrition plans and nursing records retain their author, creation/update timestamps and updating user. Access audit entries contain resource, actor, action and changed field names, without clinical text. Care validation errors omit submitted content. The audit does not store passwords, observations or dietary guidance.

## Migration and checks

Revision `a0ef5678b920` follows the existing space-weather revision `f9a1b2c3d4e5`. It adds the six account flags, new mission role values, `access_audit_events`, `nutrition_plans` and `nursing_records`. Existing accounts stay active; no global administrator is granted automatically. Downgrade requires removing new mission role assignments first.

Backend: `pytest -q`. Set `MENTAL_HEALTH_POSTGRES_TESTS=1` to include the full migration chain and isolated PostgreSQL checks. Frontend: `npm test`, `npm run typecheck`, `npm run build`, `npm run test:profiles:e2e`, `npm run test:mental-health:e2e` and `npm run test:nutrition:e2e`.
