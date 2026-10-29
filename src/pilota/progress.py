"""Live progress renderers for agent executions."""

from __future__ import annotations

import os
import sys
from contextlib import suppress
from datetime import datetime
from io import TextIOBase
from threading import Event, Lock, Thread

from pilota.models import TraceEvent


class TerminalProgress:
    """Render compact live progress in a terminal and plain updates in logs."""

    _frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(
        self,
        stream: TextIOBase | None = None,
        *,
        refresh_interval: float = 0.1,
    ) -> None:
        if refresh_interval <= 0:
            raise ValueError("refresh_interval must be greater than zero")
        self._stream = stream or sys.stderr
        self._refresh_interval = refresh_interval
        self._interactive = self._is_interactive()
        self._color = self._interactive and "NO_COLOR" not in os.environ
        self._started_at: datetime | None = None
        self._label = "Starting"
        self._frame = 0
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._line_width = 0

    def __call__(self, event: TraceEvent) -> None:
        if event.kind == "execution.started":
            self._start(event)
        elif event.kind == "model.requested":
            self._set_active(f"Thinking · model call {event.data['call']}")
        elif event.kind == "model.responded":
            self._set_label(f"Model call {event.data['call']} finished")
        elif event.kind == "tool.started":
            self._set_active(f"Running {event.data['tool']}")
        elif event.kind == "tool.completed":
            self._set_label(f"Finished {event.data['tool']}")
        elif event.kind == "human.question":
            self._end_line("?", "Waiting for input")
        elif event.kind in {"tool.failed", "tool.denied", "result.rejected"}:
            self._set_label(self._warning_label(event), "!")
        elif event.kind == "execution.completed":
            self._end_line("✓", "Done")
        elif event.kind in {"model.failed", "execution.limit_exhausted"}:
            self._end_line("✗", "Failed")
        elif event.kind == "execution.cancelled":
            self._end_line("■", "Cancelled")

    def _start(self, event: TraceEvent) -> None:
        self._stop_spinner()
        self._started_at = event.timestamp
        self._label = "Starting"
        self._frame = 0
        self._stop.clear()
        if not self._interactive:
            self._write_plain("Starting agent")

    def _set_active(self, label: str) -> None:
        self._label = label
        if self._interactive:
            self._render()
            self._start_spinner()
        else:
            self._write_plain(label)

    def _set_label(self, label: str, marker: str = "●") -> None:
        self._stop_spinner()
        self._label = label
        if self._interactive:
            self._render(marker)
        else:
            self._write_plain(label)

    def _end_line(self, marker: str, label: str) -> None:
        self._stop_spinner()
        if self._interactive:
            self._render(marker, label)
            self._stream.write("\n")
            self._stream.flush()
            self._line_width = 0
        else:
            self._write_plain(label)

    def _start_spinner(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _stop_spinner(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=0.5)
        self._thread = None

    def _spin(self) -> None:
        while not self._stop.wait(self._refresh_interval):
            self._frame = (self._frame + 1) % len(self._frames)
            self._render()

    def _render(self, marker: str | None = None, label: str | None = None) -> None:
        symbol = marker or self._frames[self._frame]
        plain_symbol = symbol
        if self._color:
            color = {"✓": "32", "✗": "31", "!": "33", "■": "33"}.get(symbol, "36")
            symbol = f"\033[{color}m{symbol}\033[0m"
        elapsed = self._elapsed()
        text = f"{symbol} {label or self._label}  {elapsed}"
        plain_text = f"{plain_symbol} {label or self._label}  {elapsed}"
        with self._lock:
            padding = " " * max(self._line_width - len(plain_text), 0)
            self._stream.write(f"\r\033[2K{text}{padding}")
            self._stream.flush()
            self._line_width = len(plain_text)

    def _write_plain(self, label: str) -> None:
        self._stream.write(f"[pilota] {label} ({self._elapsed()})\n")
        self._stream.flush()

    def _elapsed(self) -> str:
        if self._started_at is None:
            return "0.0s"
        seconds = max((datetime.now(self._started_at.tzinfo) - self._started_at).total_seconds(), 0)
        return f"{seconds:.1f}s"

    def _is_interactive(self) -> bool:
        with suppress(AttributeError):
            return bool(self._stream.isatty() and os.environ.get("TERM") != "dumb")
        return False

    @staticmethod
    def _warning_label(event: TraceEvent) -> str:
        if event.kind == "result.rejected":
            return "Result did not match the contract, retrying"
        tool = event.data.get("tool")
        return f"{tool or 'Step'} {event.kind.rsplit('.', 1)[-1]}"
