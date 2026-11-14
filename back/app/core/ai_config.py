import os

from pydantic import BaseModel, Field


class AiSettings(BaseModel):
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = "qwen2.5:3b"
    api_key: str = ""
    timeout_seconds: float = Field(default=60, gt=0, allow_inf_nan=False)

    @classmethod
    def from_environment(cls) -> "AiSettings":
        return cls(
            base_url=os.getenv("AI_BASE_URL", "http://127.0.0.1:11434/v1"),
            model=os.getenv("AI_MODEL", "qwen2.5:3b"),
            api_key=os.getenv("AI_API_KEY", ""),
            timeout_seconds=os.getenv("AI_TIMEOUT_SECONDS", "60"),
        )
