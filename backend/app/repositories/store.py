from collections.abc import Callable
from typing import Any, Protocol, TypeVar

Document = dict[str, Any]
T = TypeVar("T")


class UnitOfWork(Protocol):
    """Read before writing; all writes commit or fail together."""

    def get(self, collection: str, record_id: str) -> Document | None: ...
    def create(self, collection: str, record_id: str, data: Document) -> None: ...
    def set(self, collection: str, record_id: str, data: Document) -> None: ...


class Store(Protocol):
    def get(self, collection: str, record_id: str) -> Document | None: ...
    def list(
        self,
        collection: str,
        *,
        filters: list[tuple[str, str, Any]] | None = None,
        after_id: str | None = None,
        limit: int = 100,
    ) -> list[Document]: ...
    def atomic(self, operation: Callable[[UnitOfWork], T]) -> T: ...
