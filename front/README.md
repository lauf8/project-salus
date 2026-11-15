# Project Salus · Monitoring System

React 19 and Vite frontend for the FastAPI backend in this repository. The interface is in English and responsive, covering missions, members, exam catalog, requirements, checklist, scheduling, results, corrections and reviews, plus health, mental health, nutrition, radiation, mission risks and Predictive Intelligence.

## Run

From the backend folder (`../back`), start the API:

```sh
docker compose up --build -d
```

From this folder:

```sh
npm install
npm run dev
```

Open http://localhost:5173. The Vite proxy forwards `/api` to `http://localhost:8000`, so no CORS change is needed. The landing page is at http://localhost:5173/overview (see [LANDING_PAGE.md](../LANDING_PAGE.md)).

## Verification

```sh
npm test
npm run typecheck
npm run build
```

The static build is in `dist`. In production, configure the server or reverse proxy to forward `/api/*` to the API, removing the `/api` prefix. The development proxy is not part of the build. `npm run preview` only serves the compiled files.

## Access and permissions

The interface opens without login. The **Profile** and **User** selectors at the top choose the active identity, and the choice is saved in this browser. The API still checks every permission. See [USER_ACCESS.md](../USER_ACCESS.md).

Administrators manage the mission, members, requirements and scheduling. Flight surgeons record, correct and review results. Astronauts view their own history. Exam types follow the backend permissions, and 403 errors are shown. The checklist state comes only from the backend. Local form dates are sent in UTC with a time zone. Paginated listings are read in full; missions, catalog and directory have visual pagination.

Google Fonts are optional, with a fallback to system fonts. The application does not depend on external services to access its data.

The visual identity uses the Project Salus logo in `public/salus.png`, shown in the sidebar and as the tab icon. The image keeps its original aspect ratio.

Account profiles do not grant clinical access on their own: the administrator still assigns each person's role in the mission.

Changes to exams, requirements, catalog and scheduling require the Physician profile and mission authorization. Astronauts without the physician profile can read their own exams. Results and reviews remain protected against deletion.

## Health dashboard

The dashboard is the astronaut's home page, with 11 indicators, a body map, manual recording, Recharts charts and categorical history. Physicians follow astronauts of the missions where they are flight surgeons. See [running, permissions, endpoints and verification](../HEALTH_MONITORING.md).

## Exams and structured results

The **Exams** screen lets you search, list, view fields, and create or edit
exams linked to the existing types. Only physicians with catalog permission get
write actions. Each exam defines numeric, short or long text, selection, yes/no
and date fields, with units and required flags.

In the mission requirements, the physician chooses a registered exam and sets
how long before launch it is due. In the monitoring checklist history, the
flight surgeon records the values, laboratory references, collection and report
data, and performs the review. Astronauts only see their own results. The
backend checks the same restrictions.

The form and the history use the field version stored when the exam was
assigned. Changing the catalog does not rewrite earlier results. Reviewed
results stay immutable and can be replaced by a new performance of the exam.
The flow remains a preflight exam flow: the performance date must be before the
mission start when it is set.

The initial catalog and its migration are in the backend. Run from `back/`:

```bash
docker compose exec -T api alembic upgrade head
docker compose exec -T api python -m scripts.seed_exam_catalog
```

The seed adds 29 definitions based on NASA OCHMO-STD-100.1A, Rev. A, and keeps
existing records. The seed does not simulate any clinical result. References and
pages appear on screen; units and fields are adapted for recording, and reference
ranges are filled in from the laboratory report.

`npm test` checks result serialization, rendering of fields and history,
compatibility with legacy results and the create action according to permission.
`npm run build` validates the complete bundle.
