from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.core.ai_config import AiSettings
from app.providers.ai import AiProvider
from app.providers.openai_compatible import OpenAiCompatibleProvider
from app.routers import nutrition, auth, demo, health, medicines, notifications, preflight, spacecraft, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = AiSettings.from_environment()
    app.state.agent_instructions = (
        Path(__file__).resolve().parent.parent / "agent_instructions.md"
    ).read_text(encoding="utf-8")
    async with httpx.AsyncClient() as client:
        provider: AiProvider = OpenAiCompatibleProvider(client, settings)
        app.state.ai_provider = provider
        yield


app = FastAPI(title="Nasa Health Monitor", lifespan=lifespan)

app.include_router(users.router, prefix="/v1")
app.include_router(auth.router, prefix="/v1")
app.include_router(demo.router)
app.include_router(preflight.router, prefix="/v1")

app.include_router(health.router, prefix="/v1")

app.include_router(medicines.router, prefix="/v1")

app.include_router(notifications.router, prefix="/v1")

app.include_router(spacecraft.router, prefix="/v1")

app.include_router(nutrition.router, prefix="/v1")
