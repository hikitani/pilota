"""Structured execution tracing."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeAlias

from pilota.models import Trace, TraceEvent

ProgressCallback: TypeAlias = Callable[[TraceEvent], None]


class TraceRecorder:
    def __init__(self, progress: ProgressCallback | None = None) -> None:
        self._events: list[TraceEvent] = []
        self._progress = progress

    def record(self, kind: str, data: Mapping[str, Any] | None = None) -> None:
        event = TraceEvent(kind=kind, data=data or {})
        self._events.append(event)
        if self._progress is not None:
            self._progress(event)

    def snapshot(self) -> Trace:
        return Trace(events=tuple(self._events))
