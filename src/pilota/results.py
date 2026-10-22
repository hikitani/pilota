"""Typed result contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Generic, TypeVar

from pydantic import TypeAdapter, ValidationError

from pilota.errors import ResultContractError

T = TypeVar("T")


class ResultCodec(Generic[T]):
    """Translate between a Python type and a model-facing JSON schema."""

    def __init__(self, result_type: type[T]) -> None:
        self._adapter = TypeAdapter(result_type)

    def schema(self) -> Mapping[str, Any]:
        return self._adapter.json_schema()

    def decode(self, value: Any, *, execution_id: str | None = None) -> T:
        try:
            return self._adapter.validate_python(value)
        except ValidationError as error:
            raise ResultContractError(
                f"Final result does not satisfy the requested type: {error}",
                execution_id=execution_id,
            ) from error
