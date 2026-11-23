import asyncio
from typing import List, Dict, Any, AsyncGenerator, TypeVar, Type
from pydantic import BaseModel
from app.ai.planning.schemas import AnalysisPlan, DatasetRef, AggregateOperation, Condition

T = TypeVar("T", bound=BaseModel)

class MockAIProvider:
    """Deterministic Mock AI provider for local testing and CI."""
    async def generate(self, messages: List[Dict[str, str]], *, temperature: float = 0.0) -> str:
        last_message = messages[-1]["content"] if messages else ""
        return f"Mock AI Response: I have received and analyzed your query: '{last_message}'."

    async def generate_structured(self, messages: List[Dict[str, str]], schema: Type[T]) -> T:
        last_message = messages[-1]["content"] if messages else ""
        
        # If requested schema is AnalysisPlan, construct a tailored plan based on prompt keywords
        if issubclass(schema, AnalysisPlan):
            # Parse mock plan
            return schema(
                intent="DATA_ANALYSIS",
                question=last_message,
                datasets=[DatasetRef(file_id="default_file", alias="dataset_1")],
                filters=[],
                group_by=[],
                aggregations=[AggregateOperation(function="count", column="*", alias="total_count")],
                limit=100
            ) # type: ignore
        
        # Default empty model instance
        return schema() # type: ignore

    async def stream(self, messages: List[Dict[str, str]], *, temperature: float = 0.0) -> AsyncGenerator[str, None]:
        text = await self.generate(messages, temperature=temperature)
        words = text.split(" ")
        for word in words:
            yield word + " "
            await asyncio.sleep(0.01)

    async def health_check(self) -> bool:
        return True
