from typing import Protocol, List, Dict, Any, AsyncGenerator, TypeVar, Type
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class AIProvider(Protocol):
    async def generate(self, messages: List[Dict[str, str]], *, temperature: float = 0.0) -> str:
        """Generate a complete text response."""
        ...

    async def generate_structured(self, messages: List[Dict[str, str]], schema: Type[T]) -> T:
        """Generate a validated structured Pydantic object."""
        ...

    async def stream(self, messages: List[Dict[str, str]], *, temperature: float = 0.0) -> AsyncGenerator[str, None]:
        """Stream response chunks asynchronously."""
        ...

    async def health_check(self) -> bool:
        """Verify provider availability."""
        ...
