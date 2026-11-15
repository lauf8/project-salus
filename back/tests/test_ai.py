import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.ai_config import AiSettings
from app.main import app
from app.providers.openai_compatible import OpenAiCompatibleProvider


REPORT = "I had a headache after training"
EXTRACTION = {"symptom": "headache", "activity_context": "after training"}


@pytest.mark.parametrize("api_key", ["", "fictional-key"])
def test_provider_request(api_key):
    async def run():
        def handle(request):
            assert str(request.url) == "http://ai.test/v1/chat/completions"
            assert request.method == "POST"
            body = json.loads(request.content)
            assert body["model"] == "fictional-model"
            assert body["messages"] == [
                {"role": "system", "content": "Extract symptoms"},
                {"role": "user", "content": REPORT},
            ]
            assert request.headers.get("authorization") == (
                f"Bearer {api_key}" if api_key else None
            )
            assert request.extensions["timeout"]["read"] == 60
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(EXTRACTION)}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            provider = OpenAiCompatibleProvider(client, AiSettings(
                base_url="http://ai.test/v1/", model="fictional-model", api_key=api_key
            ))
            assert json.loads(await provider.generate("Extract symptoms", REPORT)) == EXTRACTION

    asyncio.run(run())


@pytest.mark.parametrize("scenario,expected", [
    ("success", 200), ("timeout", 504), ("unavailable", 503),
    ("http_error", 503), ("invalid_envelope", 502), ("invalid_json", 502),
    ("invalid_extraction", 502), ("wrong_type", 502), ("empty", 502),
])
def test_extraction_route(scenario, expected):
    def handle(request):
        if scenario == "timeout":
            raise httpx.ReadTimeout("fictional timeout", request=request)
        if scenario == "unavailable":
            raise httpx.ConnectError("fictional failure", request=request)
        if scenario == "http_error":
            return httpx.Response(500)
        if scenario == "invalid_envelope":
            return httpx.Response(200, json={"choices": []})
        if scenario == "invalid_json":
            return httpx.Response(200, text="invalid")
        content = {
            "invalid_extraction": '{"symptom":"headache"}',
            "wrong_type": '{"symptom":12,"activity_context":null}',
            "empty": '{"symptom":" ","activity_context":null}',
        }.get(scenario, json.dumps(EXTRACTION))
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    with TestClient(app) as client:
        assert app.state.agent_instructions.strip()
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http_client:
                app.state.ai_provider = OpenAiCompatibleProvider(http_client, AiSettings())
                response = await asyncio.to_thread(client.post, "/demo/assessments/extract", json={"context": REPORT})
                assert response.status_code == expected
                if expected == 200:
                    assert response.json() == {**EXTRACTION, "source_ids": []}
        asyncio.run(run())


def test_empty_report():
    with TestClient(app) as client:
        response = client.post("/demo/assessments/extract", json={"context": " "})
        assert response.status_code == 422
