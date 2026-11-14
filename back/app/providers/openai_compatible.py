import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.ai_config import AiSettings
from app.providers.ai import AiInvalidResponseError, AiTimeoutError, AiUnavailableError


class CompletionMessage(BaseModel):
    model_config = ConfigDict(strict=True)
    content: str = Field(min_length=1)


class CompletionChoice(BaseModel):
    message: CompletionMessage


class CompletionResponse(BaseModel):
    choices: list[CompletionChoice] = Field(min_length=1)


class OpenAiCompatibleProvider:
    def __init__(self, client: httpx.AsyncClient, settings: AiSettings):
        self.client = client
        self.settings = settings

    async def generate(self, instructions: str, context: str) -> str:
        headers = {}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        try:
            response = await self.client.post(
                f"{self.settings.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": self.settings.model,
                    "messages": [
                        {"role": "system", "content": instructions},
                        {"role": "user", "content": context},
                    ],
                    "stream": False,
                },
                timeout=self.settings.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AiTimeoutError from exc
        except httpx.HTTPError as exc:
            raise AiUnavailableError from exc
        try:
            completion = CompletionResponse.model_validate(response.json())
            content = completion.choices[0].message.content
            if not content.strip():
                raise AiInvalidResponseError
            return content
        except (ValueError, ValidationError) as exc:
            raise AiInvalidResponseError from exc
