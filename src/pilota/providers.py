"""Model provider interfaces and deterministic test doubles."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Protocol

from pilota.errors import ProviderError
from pilota.models import ModelAction, ModelRequest


class Model(Protocol):
    def respond(self, request: ModelRequest) -> ModelAction: ...


class ScriptedModel:
    """Return a predetermined sequence of actions for deterministic tests."""

    def __init__(self, actions: Iterable[ModelAction]) -> None:
        self._actions = deque(actions)
        self.requests: list[ModelRequest] = []

    def respond(self, request: ModelRequest) -> ModelAction:
        self.requests.append(request)
        if not self._actions:
            raise ProviderError("ScriptedModel has no actions remaining")
        return self._actions.popleft()
