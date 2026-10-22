"""Structured execution tracing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pilota.models import Trace, TraceEvent


class TraceRecorder:
    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def record(self, kind: str, data: Mapping[str, Any] | None = None) -> None:
        self._events.append(TraceEvent(kind=kind, data=data or {}))

    def snapshot(self) -> Trace:
        return Trace(events=tuple(self._events))
