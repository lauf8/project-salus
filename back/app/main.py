from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse

from app.core.ai_config import AiSettings
from app.providers.ai import AiProvider
from app.providers.openai_compatible import OpenAiCompatibleProvider
from app.routers import clinical_records, mission_risks, astronaut_control, care, mental_health, nutrition, auth, demo, health, medicines, notifications, preflight, radiation, space_weather, spacecraft, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = AiSettings.from_environment()
    app.state.agent_instructions = (
        Path(__file__).resolve().parent.parent / "agent_instructions.md"
    ).read_text(encoding="utf-8")
    async with httpx.AsyncClient() as client:
        provider: AiProvider = OpenAiCompatibleProvider(client, settings)
        app.state.ai_provider = provider
        # Cliente síncrono do NASA DONKI (as rotas da API são síncronas).
        with httpx.Client() as donki_http_client:
            app.state.donki_http_client = donki_http_client
            yield


app = FastAPI(title="Project Salus", lifespan=lifespan)

app.include_router(clinical_records.router, prefix="/v1")
app.include_router(mission_risks.router, prefix="/v1")
app.include_router(users.router, prefix="/v1")
app.include_router(auth.router, prefix="/v1")
app.include_router(demo.router)
app.include_router(preflight.router, prefix="/v1")

app.include_router(health.router, prefix="/v1")

app.include_router(medicines.router, prefix="/v1")

app.include_router(notifications.router, prefix="/v1")

app.include_router(spacecraft.router, prefix="/v1")

app.include_router(nutrition.router, prefix="/v1")

app.include_router(mental_health.router, prefix="/v1")

app.include_router(care.router, prefix="/v1")
app.include_router(astronaut_control.router, prefix="/v1")

app.include_router(space_weather.router, prefix="/v1")

app.include_router(radiation.router, prefix="/v1")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    if any(part in request.url.path for part in ("/mental-health/", "/nutrition-plans", "/nursing-records")):
        return JSONResponse(status_code=422, content={"detail": [{"loc": list(error["loc"]), "msg": "Invalid value", "type": error["type"]} for error in exc.errors()]})
    return await request_validation_exception_handler(request, exc)
