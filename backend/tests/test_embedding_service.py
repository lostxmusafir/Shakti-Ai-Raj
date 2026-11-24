import pytest

from app.ai.learning.embedding_service import EmbeddingService


class FakeEmbeddingProvider:
    embedding_model = "fake-embed"

    async def embed(self, texts):
        return [[float(index), 1.0] for index, _ in enumerate(texts)]


@pytest.mark.asyncio
async def test_embedding_service_validates_dimensions():
    result = await EmbeddingService.embed_examples([{"example_id": "e1", "question": "count rows"}], FakeEmbeddingProvider())
    assert result["dimension"] == 2
    assert result["records"][0]["example_id"] == "e1"
