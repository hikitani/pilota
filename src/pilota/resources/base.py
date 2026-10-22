"""External resource contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pilota.errors import ToolError
from pilota.models import ToolSpec
from pilota.tools import ToolContext


@dataclass(frozen=True)
class ResourceOperation:
    name: str
    description: str
    input_schema: Mapping[str, Any]


class Resource(Protocol):
    @property
    def operations(self) -> Mapping[str, ResourceOperation]: ...

    def invoke(self, operation: str, arguments: Mapping[str, Any]) -> Any: ...


class ResourceTool:
    def __init__(self, name: str, resource: Resource) -> None:
        self._name = name
        self._resource = resource

    @property
    def spec(self) -> ToolSpec:
        operations = self._resource.operations
        descriptions = "; ".join(
            f"{operation.name}: {operation.description}" for operation in operations.values()
        )
        return ToolSpec(
            name=f"resource_{self._name}",
            description=f"Access the {self._name!r} resource. Operations: {descriptions}",
            input_schema={
                "type": "object",
                "properties": {
                    "operation": {"enum": sorted(operations)},
                    "arguments": {"type": "object"},
                },
                "required": ["operation", "arguments"],
                "additionalProperties": False,
            },
        )

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Any:
        del context
        operation = arguments.get("operation")
        operation_arguments = arguments.get("arguments")
        if not isinstance(operation, str):
            raise ToolError("Resource operation must be a string")
        if not isinstance(operation_arguments, Mapping):
            raise ToolError("Resource arguments must be an object")
        return self._resource.invoke(operation, operation_arguments)


def resource_tools(resources: Mapping[str, Resource]) -> tuple[ResourceTool, ...]:
    return tuple(ResourceTool(name, resource) for name, resource in resources.items())
