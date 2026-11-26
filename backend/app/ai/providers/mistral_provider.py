import asyncio
import json
import logging
from typing import List, Dict, Any, AsyncGenerator, TypeVar, Type, Optional
import httpx
from pydantic import BaseModel
from app.core.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

class MistralAIProvider:
    """
    Mistral AI Provider supporting:
    - Thread-safe round-robin key rotation across multiple API keys.
    - Automatic failover and retry on HTTP 429 (rate limits) or transient network errors.
    - Model tiering: Free base model (ministral-8b-latest) and higher model (codestral-latest).
    - Structured JSON generation via response_format={"type": "json_object"}.
    - SSE token streaming.
    - Vector embeddings via mistral-embed.
    """
    def __init__(
        self,
        api_keys: Optional[List[str]] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        higher_model: Optional[str] = None,
        embedding_model: Optional[str] = None,
        timeout: float = 60.0
    ):
        if api_keys is not None:
            self.api_keys = list(api_keys)
        else:
            self.api_keys = list(settings.MISTRAL_API_KEYS)
        
        if not self.api_keys and settings.AI_API_KEY:
            self.api_keys = [settings.AI_API_KEY]
            
        self.base_url = (base_url or settings.MISTRAL_BASE_URL).rstrip("/")
        self.default_model = default_model or settings.MISTRAL_DEFAULT_MODEL
        self.higher_model = higher_model or settings.MISTRAL_HIGHER_MODEL
        self.embedding_model = embedding_model or settings.MISTRAL_EMBEDDING_MODEL
        self.timeout = timeout
        
        self._key_index = 0
        self._lock = asyncio.Lock()
        self._stats: Dict[str, Dict[str, int]] = {
            k: {"requests": 0, "errors": 0, "rate_limits": 0, "success": 0} for k in self.api_keys
        }

    async def get_next_key(self) -> str:
        """Select the next key in round-robin fashion."""
        if not self.api_keys:
            raise ValueError("No Mistral API keys configured.")
        async with self._lock:
            key = self.api_keys[self._key_index % len(self.api_keys)]
            self._key_index += 1
            return key

    async def _call_with_failover(
        self,
        endpoint: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute POST with round-robin rotation and automatic failover on 429/5xx."""
        num_keys = len(self.api_keys)
        attempts = max(num_keys, 1)
        last_exception = None

        for attempt in range(attempts):
            key = await self.get_next_key()
            if key not in self._stats:
                self._stats[key] = {"requests": 0, "errors": 0, "rate_limits": 0, "success": 0}
            self._stats[key]["requests"] += 1
            
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 429:
                        self._stats[key]["rate_limits"] += 1
                        retry_after = resp.headers.get("retry-after")
                        delay = min(float(retry_after), 3.0) if retry_after and retry_after.replace(".", "", 1).isdigit() else 0.5 * (attempt + 1)
                        logger.warning(
                            f"Mistral key ...{key[-6:]} rate limited (429). "
                            f"Backing off {delay:.1f}s and rotating to next key (attempt {attempt+1}/{attempts})."
                        )
                        last_exception = httpx.HTTPStatusError("429 Rate Limit", request=resp.request, response=resp)
                        if attempt + 1 < attempts:
                            await asyncio.sleep(delay)
                        continue
                    if resp.status_code in (401, 402, 403) or resp.status_code >= 500:
                        self._stats[key]["errors"] += 1
                        logger.warning(
                            f"Provider key ...{key[-6:]} returned HTTP {resp.status_code}. "
                            f"Rotating to next key (attempt {attempt+1}/{attempts})."
                        )
                        last_exception = httpx.HTTPStatusError(f"{resp.status_code} Error", request=resp.request, response=resp)
                        continue
                    resp.raise_for_status()
                    self._stats[key]["success"] += 1
                    return resp.json()
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                self._stats[key]["errors"] += 1
                logger.warning(f"Mistral network error on key ...{key[-6:]}: {exc}. Rotating.")
                last_exception = exc
                continue

        if last_exception:
            raise last_exception
        raise RuntimeError("Mistral API call failed with all available keys.")

    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.0,
        use_higher_model: bool = False,
        model: Optional[str] = None
    ) -> str:
        """Generate text using round-robin keys with base or higher model."""
        chosen_model = model or (self.higher_model if use_higher_model else self.default_model)
        payload = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature
        }
        data = await self._call_with_failover("chat/completions", payload)
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "") or ""
        return ""

    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        schema: Type[T],
        *,
        model: Optional[str] = None
    ) -> T:
        """Generate validated Pydantic object using higher model and response_format json_object."""
        chosen_model = model or self.higher_model
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        system_instruction = (
            "You are a structured data analysis and planning assistant.\n"
            f"You MUST generate a valid JSON object strictly conforming to this JSON Schema:\n{schema_json}\n"
            "Return ONLY the raw JSON object. Do not wrap in markdown code blocks."
        )
        augmented_messages = [{"role": "system", "content": system_instruction}] + list(messages)
        payload = {
            "model": chosen_model,
            "messages": augmented_messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        data = await self._call_with_failover("chat/completions", payload)
        choices = data.get("choices", [])
        raw_text = choices[0].get("message", {}).get("content", "").strip() if choices else ""
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        return schema.model_validate_json(raw_text.strip())

    async def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.0,
        use_higher_model: bool = False,
        model: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens with SSE and key rotation failover."""
        chosen_model = model or (self.higher_model if use_higher_model else self.default_model)
        payload = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }
        num_keys = len(self.api_keys)
        attempts = max(num_keys, 1)
        last_exception = None

        for attempt in range(attempts):
            key = await self.get_next_key()
            if key not in self._stats:
                self._stats[key] = {"requests": 0, "errors": 0, "rate_limits": 0, "success": 0}
            self._stats[key]["requests"] += 1
            
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream"
            }
            url = f"{self.base_url}/chat/completions"
            
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    async with client.stream("POST", url, json=payload, headers=headers) as resp:
                        if resp.status_code == 429:
                            self._stats[key]["rate_limits"] += 1
                            retry_after = resp.headers.get("retry-after")
                            delay = min(float(retry_after), 3.0) if retry_after and retry_after.replace(".", "", 1).isdigit() else 0.5 * (attempt + 1)
                            logger.warning(
                                f"Mistral stream rate limited on key ...{key[-6:]}. "
                                f"Backing off {delay:.1f}s and rotating (attempt {attempt+1}/{attempts})."
                            )
                            last_exception = httpx.HTTPStatusError("429 Rate Limit", request=resp.request, response=resp)
                            if attempt + 1 < attempts:
                                await asyncio.sleep(delay)
                            continue
                        if resp.status_code >= 500:
                            self._stats[key]["errors"] += 1
                            logger.warning(f"Mistral stream server error {resp.status_code}. Rotating.")
                            last_exception = httpx.HTTPStatusError(f"{resp.status_code} Server Error", request=resp.request, response=resp)
                            continue
                        resp.raise_for_status()
                        self._stats[key]["success"] += 1
                        
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if not line or line.startswith(":"):
                                continue
                            if line.startswith("data: "):
                                data_str = line[6:].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    choices = chunk.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                except json.JSONDecodeError:
                                    continue
                        return
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                self._stats[key]["errors"] += 1
                logger.warning(f"Mistral stream network error on key ...{key[-6:]}: {exc}. Rotating.")
                last_exception = exc
                continue

        if last_exception:
            raise last_exception
        raise RuntimeError("Mistral streaming failed on all available keys.")

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate vector embeddings for input texts using mistral-embed."""
        if not texts:
            return []
        payload = {
            "model": self.embedding_model,
            "input": texts
        }
        data = await self._call_with_failover("embeddings", payload)
        items = data.get("data", [])
        return [item["embedding"] for item in items]

    async def embed_query(self, text: str) -> List[float]:
        """Embed a single query string."""
        results = await self.embed([text])
        return results[0] if results else []

    async def health_check(self) -> bool:
        """Verify availability by executing a lightweight ping."""
        if not self.api_keys:
            return False
        try:
            payload = {
                "model": self.default_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
                "temperature": 0.0
            }
            data = await self._call_with_failover("chat/completions", payload)
            return bool(data.get("choices"))
        except Exception as e:
            logger.error(f"Mistral health check failed: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Retrieve operational statistics for round-robin monitoring."""
        return {
            "keys_count": len(self.api_keys),
            "current_index": self._key_index,
            "default_model": self.default_model,
            "higher_model": self.higher_model,
            "embedding_model": self.embedding_model,
            "key_stats": {
                f"...{k[-6:]}": stats for k, stats in self._stats.items()
            }
        }
