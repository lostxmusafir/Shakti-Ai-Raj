from typing import Protocol, List, Dict, Any, AsyncGenerator, TypeVar, Type, Optional
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class AIProvider(Protocol):
    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.0,
        use_higher_model: bool = False,
        model: Optional[str] = None
    ) -> str:
        """Generate a complete text response."""
        ...

    async def generate_structured(
        self,
        messages: List[Dict[str, str]],
        schema: Type[T],
        *,
        model: Optional[str] = None
    ) -> T:
        """Generate a validated structured Pydantic object."""
        ...

    async def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.0,
        use_higher_model: bool = False,
        model: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Stream response chunks asynchronously."""
        ...

    async def health_check(self) -> bool:
        """Verify provider availability."""
        ...
