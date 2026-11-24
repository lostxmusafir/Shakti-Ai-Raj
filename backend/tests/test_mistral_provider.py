import pytest
import asyncio
import os
from unittest.mock import patch, MagicMock
from pydantic import BaseModel
import httpx
from app.ai.providers.mistral_provider import MistralAIProvider
from app.core.config import settings

SAMPLE_KEYS = ["test-key-a", "test-key-b", "test-key-c"]

class MockAnalysisResult(BaseModel):
    summary: str
    confidence_score: float

@pytest.mark.asyncio
async def test_round_robin_key_rotation():
    provider = MistralAIProvider(api_keys=SAMPLE_KEYS)
    
    k1 = await provider.get_next_key()
    k2 = await provider.get_next_key()
    k3 = await provider.get_next_key()
    k4 = await provider.get_next_key()
    
    assert k1 == SAMPLE_KEYS[0]
    assert k2 == SAMPLE_KEYS[1]
    assert k3 == SAMPLE_KEYS[2]
    assert k4 == SAMPLE_KEYS[0]  # wrapped around to 0

@pytest.mark.asyncio
async def test_automatic_failover_on_429():
    provider = MistralAIProvider(api_keys=SAMPLE_KEYS)
    
    call_count = 0
    used_auth_headers = []

    def mock_post(url, json=None, headers=None, **kwargs):
        nonlocal call_count
        call_count += 1
        used_auth_headers.append(headers.get("Authorization"))
        
        # First key returns 429 rate limit
        if call_count == 1:
            req = httpx.Request("POST", url)
            return httpx.Response(429, request=req, json={"message": "Rate limit exceeded"})
        
        # Second key succeeds with 200
        req = httpx.Request("POST", url)
        return httpx.Response(200, request=req, json={
            "choices": [{"message": {"content": "Failover succeeded!"}}]
        })

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        result = await provider.generate([{"role": "user", "content": "hello"}])
        assert result == "Failover succeeded!"
        assert call_count == 2
        assert used_auth_headers[0] == f"Bearer {SAMPLE_KEYS[0]}"
        assert used_auth_headers[1] == f"Bearer {SAMPLE_KEYS[1]}"
        
        # Verify provider stats tracked the 429
        stats = provider.get_stats()
        key1_masked = f"...{SAMPLE_KEYS[0][-6:]}"
        key2_masked = f"...{SAMPLE_KEYS[1][-6:]}"
        assert stats["key_stats"][key1_masked]["rate_limits"] == 1
        assert stats["key_stats"][key2_masked]["success"] == 1

@pytest.mark.asyncio
async def test_structured_generation_with_schema():
    provider = MistralAIProvider(api_keys=SAMPLE_KEYS)
    expected_obj = {"summary": "Analysis completed safely.", "confidence_score": 0.99}

    def mock_post(url, json=None, headers=None, **kwargs):
        req = httpx.Request("POST", url)
        assert json["model"] == provider.higher_model
        assert json.get("response_format") == {"type": "json_object"}
        return httpx.Response(200, request=req, json={
            "choices": [{"message": {"content": str(expected_obj).replace("'", '"')}}]
        })

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        structured = await provider.generate_structured(
            [{"role": "user", "content": "analyze"}],
            MockAnalysisResult
        )
        assert isinstance(structured, MockAnalysisResult)
        assert structured.summary == "Analysis completed safely."
        assert structured.confidence_score == 0.99

@pytest.mark.asyncio
async def test_embed_mock():
    provider = MistralAIProvider(api_keys=SAMPLE_KEYS)
    mock_embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    def mock_post(url, json=None, headers=None, **kwargs):
        req = httpx.Request("POST", url)
        assert json["model"] == provider.embedding_model
        return httpx.Response(200, request=req, json={
            "data": [{"embedding": vec} for vec in mock_embeddings]
        })

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        vectors = await provider.embed(["text1", "text2"])
        assert vectors == mock_embeddings

@pytest.mark.asyncio
async def test_stream_mock():
    provider = MistralAIProvider(api_keys=SAMPLE_KEYS)
    
    chunks = ["Data", " analysis", " completed"]

    async def mock_aiter_lines():
        for c in chunks:
            yield f'data: {{"choices": [{{"delta": {{"content": "{c}"}}}}]}}'
        yield 'data: [DONE]'

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = mock_aiter_lines
    mock_resp.raise_for_status = MagicMock()

    class MockStreamContext:
        async def __aenter__(self):
            return mock_resp
        async def __aexit__(self, exc_type, exc, tb):
            pass

    with patch("httpx.AsyncClient.stream", return_value=MockStreamContext()):
        collected = []
        async for delta in provider.stream([{"role": "user", "content": "stream test"}]):
            collected.append(delta)
        assert "".join(collected) == "Data analysis completed"

@pytest.mark.asyncio
async def test_live_mistral_health_check_and_generation():
    """Optional live test; credentials and opt-in flag are required."""
    if os.getenv("RUN_LIVE_MISTRAL_TESTS", "").lower() not in {"1", "true", "yes"}:
        pytest.skip("Live Mistral checks are opt-in via RUN_LIVE_MISTRAL_TESTS.")
    provider = MistralAIProvider(api_keys=SAMPLE_KEYS)
    
    try:
        # 1. Health check
        is_healthy = await provider.health_check()
        assert is_healthy is True

        # 2. Brief wait to avoid bursting free tier per-minute limits
        await asyncio.sleep(1.0)

        # 3. Embedding generation with mistral-embed
        vectors = await provider.embed(["Financial compliance policy rule"])
        assert len(vectors) == 1
        assert len(vectors[0]) > 0
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            pytest.skip("Mistral free tier rate limit encountered during live check; provider rotation logic verified in unit tests.")
        raise
