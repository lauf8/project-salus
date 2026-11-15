# Project Salus

**To predict is to protect.**

Project Salus combines astronauts' physical and mental health data, spacecraft conditions and NASA space weather events. It uses artificial intelligence to anticipate risks and alert the medical team before they become problems.

This guide explains how to install and run the project on your own machine.

---

## ⚠️ A LOCAL AI IS REQUIRED

> **PROJECT SALUS MUST RUN WITH A LOCAL AI (OLLAMA) ON THE SAME MACHINE OR NETWORK.**
>
> **THE SYSTEM IS DESIGNED TO RUN ON BOARD A SPACECRAFT. FAR FROM EARTH, COMMUNICATION IS SLOW, LIMITED AND CAN BE LOST AT ANY MOMENT. THE CREW CANNOT DEPEND ON A CLOUD AI SERVICE ON EARTH TO RECEIVE A RECOMMENDATION.**
>
> **ALL AI PROCESSING (EXPLANATIONS, DOCUMENT SEARCH AND RECOMMENDATIONS) HAPPENS LOCALLY. NO HEALTH DATA LEAVES THE SPACECRAFT.**

If the local AI is not running, the predictions, rules and clinical alerts keep working, but AI explanations and NASA document evidence are not generated.

---

## What you need

| Tool | Version | Used for |
| --- | --- | --- |
| [Git](https://git-scm.com/downloads) | any recent | Download the project |
| [Docker](https://docs.docker.com/get-docker/) with Docker Compose | Docker 24 or newer | Run PostgreSQL, the API and the background workers |
| [Node.js](https://nodejs.org/) | 18 or newer (20 LTS recommended) | Run the web interface |
| [Ollama](https://ollama.com/download) | any recent | **Local AI (required)** |

Recommended hardware: 8 GB of RAM or more and about 10 GB of free disk space for Docker images, the database and the AI models.

---

## 1. Download the project

```bash
git clone https://github.com/lauf8/project-salus.git
```

```bash
cd project-salus
```

The repository has two parts:

- `back/`: FastAPI API, PostgreSQL database and background workers (Docker).
- `front/`: React web interface (Vite).

---

## 2. Install and start the local AI (Ollama)

1. Install Ollama from https://ollama.com/download.
2. Download the two models used by Salus:

```bash
ollama pull qwen2.5:3b
```

```bash
ollama pull all-minilm
```

- `qwen2.5:3b` writes explanations and recommendations.
- `all-minilm` builds the search index of NASA reference documents.

3. Make sure Ollama is running:

```bash
ollama list
```

Both models must appear in the list.

### Linux only: let Docker reach Ollama

The API runs inside Docker and reaches Ollama at `host.docker.internal:11434`. On Linux, Ollama listens only on `127.0.0.1` by default, so containers cannot reach it. Make it listen on all interfaces:

```bash
sudo systemctl edit ollama
```

Add these lines, save and close:

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
```

Then restart it:

```bash
sudo systemctl restart ollama
```

On macOS and Windows with Docker Desktop, no change is needed.

---

## 3. Configure the backend

```bash
cd back
```

```bash
cp .env.example .env
```

Open `back/.env` and review the values. For a local installation the defaults work. You may want to change:

| Variable | What it is |
| --- | --- |
| `POSTGRES_PASSWORD` | Database password. Choose your own. |
| `SECRET_KEY` | Secret used to sign sessions. Choose a long random value. |
| `NASA_API_KEY` | Free key from https://api.nasa.gov for NASA DONKI space weather. `DEMO_KEY` works with a low request limit. |
| `AI_MODEL` | Local generation model. Default: `qwen2.5:3b`. |

Never commit the `.env` file. It is already ignored by Git.

---

## 4. Start the backend

From `back/`:

```bash
docker compose up --build -d
```

The first start takes a few minutes. It:

1. starts PostgreSQL 17;
2. applies all database migrations;
3. imports the public NASA reference knowledge;
4. starts the API and the two background workers (`risk-worker` and `predictive-worker`).

Check that everything is up:

```bash
docker compose ps
```

Follow the API log if something fails:

```bash
docker compose logs -f api
```

When it is ready:

- API: http://127.0.0.1:8000
- Interactive API documentation: http://127.0.0.1:8000/docs

---

## 5. Load demonstration data

A new database is empty. To explore the system, load the 50 fictional missions used in the demonstrations. From `back/`:

```bash
docker compose exec -T -e SALUS_SYNTHETIC_ENV=development api python -m scripts.seed_synthetic_missions --publish --evaluate --output data/synthetic_missions_public
```

Index the NASA reference documents so the local AI can cite them:

```bash
docker compose exec -T api python -m scripts.index_nasa_references
```

Run one prediction cycle right away, instead of waiting for the worker:

```bash
docker compose exec -T api python -m scripts.predictive_worker
```

All demonstration records are fictional. They do not represent real people or real missions.

---

## 6. Start the web interface

Open a new terminal and go to `front/`:

```bash
cd front
```

```bash
npm install
```

```bash
npm run dev
```

Open http://localhost:5173.

The interface opens without a password. Use the two selectors at the top right, **Perfil** (profile) and **Usuário** (user), to choose who you are. For example:

- **Perfil: Mission administrator → Usuário: Rafael Andrade** sees all 50 demonstration missions.
- **Perfil: Physician → Usuário: Helena Monteiro** sees crew health, clinical records and predictions.

Each profile only sees what its role allows. See [USER_ACCESS.md](USER_ACCESS.md) for the full permission model.

---

## 7. Check that the local AI is connected

Check that the API container can reach Ollama. From `back/`:

```bash
docker compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags').read().decode())"
```

The answer must list `qwen2.5:3b` and `all-minilm`. If it fails, go back to [step 2](#2-install-and-start-the-local-ai-ollama).

As a mission administrator, you can also open a mission's risk documents in the interface and click **Check Ollama models**.

---

## 8. Open the landing page

The project presentation page runs with the same web interface. With `npm run dev` running, open:

- http://localhost:5173/overview for the landing page.
- http://localhost:5173/overview?tour for the narrated tour. The page scrolls through each section in step with the presentation narration (42 seconds by default).
- http://localhost:5173/overview?tour=50 to set another tour length in seconds, matching the length of your audio.

The tour does not play audio. Start the narration and open the page at the same time. Press any key to stop the automatic scrolling.

The landing page does not need the backend or the local AI. Content, narration timing and verification are described in [LANDING_PAGE.md](LANDING_PAGE.md).

---

## Everyday commands

From `back/`:

| Action | Command |
| --- | --- |
| Stop everything (data is kept) | `docker compose down` |
| Start again | `docker compose up -d` |
| See the logs | `docker compose logs -f api` |
| Apply new migrations after an update | `docker compose exec -T api alembic upgrade head` |
| Run one prediction cycle | `docker compose exec -T api python -m scripts.predictive_worker` |
| Evaluate prediction models without registering them | `docker compose exec -T api python -m scripts.train_prediction_models --dry-run` |

From `front/`:

| Action | Command |
| --- | --- |
| Start the interface | `npm run dev` |
| Run the tests | `npm test` |
| Build for production | `npm run build` |
| Verify the landing page in a browser | `npm run test:overview:e2e` |

`docker compose down` keeps the database. Do not delete Docker volumes to fix an error; you would lose all data.

---

## Troubleshooting

| Problem | What to do |
| --- | --- |
| AI explanations say "no documentary evidence" or "RAG unavailable" | Ollama is not running or not reachable. Run `ollama list`, check step 2 (on Linux, `OLLAMA_HOST=0.0.0.0`) and run `index_nasa_references` again. |
| `docker compose up` fails with "port is already allocated" | Another program uses port 5432 or 8000. Stop it, or change `PG_PORT` and the ports in `back/compose.yaml` for your machine only. |
| The interface shows network errors | The API is not running. Check `docker compose ps` in `back/`. The interface expects the API at `http://localhost:8000`. |
| The interface opens but has no missions | Load the demonstration data (step 5). |
| Space weather import fails | `DEMO_KEY` reached its limit. Get a free key at https://api.nasa.gov and set `NASA_API_KEY` in `back/.env`, then run `docker compose up -d`. |

---

## Learn more

| Topic | Document |
| --- | --- |
| Predictive Intelligence: how risks are anticipated, models, limits | [PREDICTIVE_INTELLIGENCE.md](PREDICTIVE_INTELLIGENCE.md) |
| Mission risks, Ollama configuration and NASA document search | [MISSION_RISKS.md](MISSION_RISKS.md) |
| Health monitoring and alerts | [HEALTH_MONITORING.md](HEALTH_MONITORING.md), [HEALTH_ALERTS.md](HEALTH_ALERTS.md) |
| Mental health | [MENTAL_HEALTH.md](MENTAL_HEALTH.md) |
| Space weather (NASA DONKI) and radiation | [SPACE_WEATHER.md](SPACE_WEATHER.md) |
| Spacecraft | [SPACECRAFT.md](SPACECRAFT.md) |
| Profiles and permissions | [USER_ACCESS.md](USER_ACCESS.md) |
| The 50 synthetic missions | [SYNTHETIC_MISSIONS.md](SYNTHETIC_MISSIONS.md) |
| Landing page and narrated tour | [LANDING_PAGE.md](LANDING_PAGE.md) |
| Backend details | [back/README.md](back/README.md) |

---

## Safety notice

Project Salus is a research prototype. Its predictions are preventive attention indicators for human review. They are not diagnoses, never lower or close a clinical alert, and do not replace the judgment of the medical team.
