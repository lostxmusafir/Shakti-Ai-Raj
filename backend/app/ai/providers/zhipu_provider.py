from typing import List, Optional
from app.core.config import settings
from app.ai.providers.mistral_provider import MistralAIProvider


class ZhipuAIProvider(MistralAIProvider):
    """
    Zhipu AI (BigModel GLM) Provider reusing thread-safe round-robin key rotation
    and automatic 429/5xx failover across multiple Zhipu API keys.
    """

    def __init__(
        self,
        api_keys: Optional[List[str]] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: float = 60.0,
    ):
        keys = list(api_keys) if api_keys is not None else list(settings.ZHIPU_API_KEYS)
        model = default_model or settings.ZHIPU_DEFAULT_MODEL
        super().__init__(
            api_keys=keys,
            base_url=base_url or settings.ZHIPU_BASE_URL,
            default_model=model,
            higher_model=model,
            embedding_model=model,
            timeout=timeout,
        )
