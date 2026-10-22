"""Convenient public API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from threading import Event
from typing import Any, TypeVar

from pilota.execution import run_agent
from pilota.instructions import InstructionInput
from pilota.models import Limits
from pilota.providers import Model
from pilota.resources import Resource
from pilota.tools import Tool, WorkspaceHandle

T = TypeVar("T")


def agent(
    task: str,
    *,
    model: Model,
    returns: type[T],
    context: Mapping[str, Any] | None = None,
    resources: Mapping[str, Resource] | None = None,
    instructions: Sequence[InstructionInput] | None = None,
    tools: Sequence[Tool] | None = None,
    workspace: WorkspaceHandle | None = None,
    limits: Limits | None = None,
    cancel_event: Event | None = None,
) -> T:
    return run_agent(
        task,
        model=model,
        returns=returns,
        context=context,
        resources=resources,
        instructions=instructions,
        tools=tools,
        workspace=workspace,
        limits=limits,
        cancel_event=cancel_event,
    ).value
