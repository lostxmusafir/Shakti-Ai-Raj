from __future__ import annotations

from typing import Any, Dict, List, Protocol


class EmbeddingProvider(Protocol):
    async def embed(self, texts: List[str]) -> List[List[float]]:
        ...


class EmbeddingService:
    """Provider adapter with dimension validation; Atlas storage is optional."""

    @staticmethod
    async def embed_examples(examples: List[Dict[str, Any]], provider: EmbeddingProvider) -> Dict[str, Any]:
        texts = [str(example.get("question", "")) for example in examples]
        vectors = await provider.embed(texts)
        if len(vectors) != len(texts):
            raise ValueError("Embedding provider returned the wrong number of vectors.")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) > 1:
            raise ValueError("Embedding provider returned inconsistent vector dimensions.")
        return {
            "model": getattr(provider, "embedding_model", "configured_provider"),
            "dimension": next(iter(dimensions), 0),
            "records": [
                {"example_id": example.get("example_id"), "embedding": vector}
                for example, vector in zip(examples, vectors)
            ],
            "storage": "caller_managed_atlas_vector_search_or_local_fallback",
        }
