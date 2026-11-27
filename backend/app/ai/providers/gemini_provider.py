import json
import logging
from typing import List, Dict, Any, AsyncGenerator, TypeVar, Type, Optional
import httpx
from pydantic import BaseModel
from app.core.config import settings
from app.ai.providers.base import AIProvider
from app.ai.providers.mock_provider import MockAIProvider

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

class GeminiAIProvider:
    def __init__(self, api_key: str = settings.AI_API_KEY, model: str = settings.AI_MODEL):
        self.api_key = api_key
        self.model = model
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.0,
        use_higher_model: bool = False,
        model: Optional[str] = None
    ) -> str:
        if not self.api_key:
            logger.warning("No GEMINI_API_KEY set. Falling back to mock response.")
            return "Gemini API key not configured. Running in fallback mode."

        contents = []
        for msg in messages:
            role = "user" if msg["role"] in ["user", "system"] else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        payload = {
            "contents": contents,
            "generationConfig": {"temperature": temperature}
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.base_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join([p.get("text", "") for p in parts])
            return ""

    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        schema: Type[T],
        *,
        model: Optional[str] = None
    ) -> T:
        schema_json = json.dumps(schema.model_json_schema())
        augmented_messages = list(messages)
        augmented_messages.append({
            "role": "system",
            "content": f"You MUST reply with ONLY a raw valid JSON object adhering strictly to this JSON Schema:\n{schema_json}\nDo not wrap in markdown quotes."
        })
        text_resp = await self.generate(augmented_messages, temperature=0.0)
        clean = text_resp.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.endswith("```"):
            clean = clean[:-3]
        parsed = json.loads(clean.strip())
        return schema.model_validate(parsed)

    async def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.0,
        use_higher_model: bool = False,
        model: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        resp = await self.generate(messages, temperature=temperature)
        for chunk in resp.split(" "):
            yield chunk + " "

    async def health_check(self) -> bool:
        return bool(self.api_key)

_TIER_PROVIDERS: Dict[str, AIProvider] = {}


def get_ai_provider() -> AIProvider:
    provider_name = settings.AI_PROVIDER.lower().strip()
    if provider_name == "mistral":
        from app.ai.providers.mistral_provider import MistralAIProvider
        return MistralAIProvider()
    elif provider_name == "zhipu":
        from app.ai.providers.zhipu_provider import ZhipuAIProvider
        return ZhipuAIProvider()
    elif provider_name == "ollama":
        from app.ai.providers.ollama_provider import OllamaAIProvider
        return OllamaAIProvider()
    elif provider_name == "gemini" and settings.AI_API_KEY:
        return GeminiAIProvider()
    return MockAIProvider()


def get_ai_provider_for_tier(ai_tier: Optional[str] = None) -> AIProvider:
    tier = (ai_tier or "low").lower().strip()
    if tier in _TIER_PROVIDERS:
        return _TIER_PROVIDERS[tier]
    if tier == "pro":
        from app.ai.providers.zhipu_provider import ZhipuAIProvider
        provider = ZhipuAIProvider()
    elif tier == "low":
        from app.ai.providers.zhipu_provider import ZhipuAIProvider
        provider = ZhipuAIProvider()
    elif tier == "local":
        from app.ai.providers.ollama_provider import OllamaAIProvider
        provider = OllamaAIProvider()
    else:
        provider = get_ai_provider()
    _TIER_PROVIDERS[tier] = provider
    return provider
