import json

import httpx
import pytest
from pydantic import BaseModel

from app.ai.providers.ollama_provider import OllamaAIProvider


class Answer(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_ollama_provider_supports_chat_and_structured_json():
    def handler(request: httpx.Request):
        payload = json.loads(request.content)
        if payload.get("format") == "json":
            content = json.dumps({"value": 7})
        else:
            content = "local response"
        return httpx.Response(200, json={"message": {"content": content}})

    provider = OllamaAIProvider(transport=httpx.MockTransport(handler))
    assert await provider.generate([{"role": "user", "content": "hello"}]) == "local response"
    result = await provider.generate_structured([{"role": "user", "content": "number"}], Answer)
    assert result.value == 7


@pytest.mark.asyncio
async def test_ollama_health_check_uses_local_tags_endpoint():
    def handler(request: httpx.Request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": []})

    provider = OllamaAIProvider(transport=httpx.MockTransport(handler))
    assert await provider.health_check() is True
