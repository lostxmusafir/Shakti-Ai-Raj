import json
import logging
from typing import AsyncGenerator, Dict, List, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel

from app.ai.providers.base import AIProvider
from app.core.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class OllamaAIProvider:
    """Local Ollama chat provider with no API key or paid service dependency."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_DEFAULT_MODEL
        self.timeout = timeout or settings.OLLAMA_TIMEOUT_SECONDS
        self.transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self.transport)

    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.0,
        use_higher_model: bool = False,
        model: Optional[str] = None,
    ) -> str:
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        async with self._client() as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        return str(data.get("message", {}).get("content", "") or "")

    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        schema: Type[T],
        *,
        model: Optional[str] = None,
    ) -> T:
        schema_json = json.dumps(schema.model_json_schema())
        augmented = list(messages)
        augmented.append({
            "role": "system",
            "content": (
                "Return only one valid JSON object matching this schema. "
                f"Do not use markdown fences. Schema: {schema_json}"
            ),
        })
        payload = {
            "model": model or self.model,
            "messages": augmented,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        async with self._client() as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        raw = str(data.get("message", {}).get("content", "") or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
        return schema.model_validate_json(raw.strip())

    async def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.0,
        use_higher_model: bool = False,
        model: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }
        async with self._client() as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("Ignoring malformed Ollama stream line")
                        continue
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if data.get("done"):
                        break

    async def health_check(self) -> bool:
        try:
            async with self._client() as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
            return True
        except (httpx.HTTPError, OSError) as exc:
            logger.info("Ollama is unavailable: %s", exc)
            return False
