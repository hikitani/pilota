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
    """Render compact live progress in a terminal and plain updates in logs.

    One instance can be shared by every agent call of a workflow. Each execution is numbered as a
    step, labelled with the first line of its task, and ends with a one-line outcome: a usage
    summary, the failure reason, or the cancellation boundary.
    """

    _frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
    _title_width = 32
    _detail_width = 120

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
        self._step = 0
        self._title = ""
        self._model_calls = 0
        self._tool_calls = 0
        self._artifacts = 0
        self._replayed = False
        self._finished = False

    def __call__(self, event: TraceEvent) -> None:
        kind = event.kind
        data = event.data
        if kind == "execution.started":
            self._start(event)
        elif self._finished:
            return
        elif kind == "model.requested":
            self._model_calls += 1
            self._set_active(f"Thinking · model call {data.get('call', self._model_calls)}")
        elif kind == "model.responded":
            self._set_label(f"Model call {data.get('call', self._model_calls)} finished")
        elif kind == "tool.started":
            self._tool_calls += 1
            self._set_active(f"Running {data.get('tool', 'tool')}")
        elif kind == "tool.completed":
            self._set_label(f"Finished {data.get('tool', 'tool')}")
        elif kind == "human.question":
            self._end_line("?", "Waiting for input")
        elif kind == "human.answer":
            self._set_label(self._answer_label(event))
        elif kind == "journal.replayed":
            replayed = data.get("kind", "step")
            self._replayed = self._replayed or replayed == "agent"
            self._set_label(f"Replayed {replayed} from journal")
        elif kind == "journal.replay_completed":
            self._set_label("Journal replay complete; continuing live")
        elif kind.startswith("artifact."):
            self._artifacts += 1
        elif kind in {"tool.failed", "tool.denied", "result.rejected"}:
            self._set_label(self._warning_label(event), "!")
        elif kind == "execution.completed":
            self._finish("✓", self._summary())
        elif kind == "model.failed":
            self._finish("✗", f"Model call failed: {self._detail(data.get('error'))}")
        elif kind == "execution.limit_exhausted":
            limit = str(data.get("limit", "execution")).replace("_", " ")
            self._finish("✗", f"{limit.capitalize()} limit exhausted")
        elif kind == "execution.cancelled":
            boundary = data.get("boundary")
            suffix = f" {str(boundary).replace('_', ' ')}" if boundary else ""
            self._finish("■", f"Cancelled{suffix}")

    def _start(self, event: TraceEvent) -> None:
        self._stop_spinner()
        if self._interactive and self._line_width:
            self._stream.write("\n")
            self._line_width = 0
        self._started_at = event.timestamp
        self._step += 1
        self._title = self._first_line(event.data.get("task"))
        self._label = "Starting"
        self._frame = 0
        self._model_calls = 0
        self._tool_calls = 0
        self._artifacts = 0
        self._replayed = False
        self._finished = False
        self._stop.clear()
        if not self._interactive:
            title = self._shorten(self._title, self._detail_width)
            self._write_plain(f"Started: {title}" if title else "Started")

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

    def _finish(self, marker: str, label: str) -> None:
        self._finished = True
        self._end_line(marker, label)

    def _end_line(self, marker: str, label: str) -> None:
        self._stop_spinner()
        if self._interactive:
            self._render(marker, label, truncate=False)
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

    def _render(
        self,
        marker: str | None = None,
        label: str | None = None,
        *,
        truncate: bool = True,
    ) -> None:
        symbol = marker or self._frames[self._frame]
        plain_symbol = symbol
        if self._color:
            color = {"✓": "32", "✗": "31", "!": "33", "■": "33"}.get(symbol, "36")
            symbol = f"\033[{color}m{symbol}\033[0m"
        elapsed = self._elapsed()
        body = self._step_prefix() + (label or self._label)
        if truncate:
            # The line is redrawn with a carriage return, so it must never wrap.
            available = self._columns() - 1 - len(plain_symbol) - 1 - 2 - len(elapsed)
            body = self._shorten(body, max(available, 1))
        text = f"{symbol} {body}  {elapsed}"
        plain_text = f"{plain_symbol} {body}  {elapsed}"
        with self._lock:
            padding = " " * max(self._line_width - len(plain_text), 0)
            self._stream.write(f"\r\033[2K{text}{padding}")
            self._stream.flush()
            self._line_width = len(plain_text)

    def _write_plain(self, label: str) -> None:
        prefix = f"[pilota #{self._step}]" if self._step else "[pilota]"
        self._stream.write(f"{prefix} {label} ({self._elapsed()})\n")
        self._stream.flush()

    def _step_prefix(self) -> str:
        if not self._step:
            return ""
        if not self._title:
            return f"#{self._step} "
        return f"#{self._step} {self._shorten(self._title, self._title_width)} · "

    def _summary(self) -> str:
        if self._replayed:
            return "Done · replayed from journal"
        parts = [self._count(self._model_calls, "model call")]
        if self._tool_calls:
            parts.append(self._count(self._tool_calls, "tool call"))
        if self._artifacts:
            parts.append(f"{self._count(self._artifacts, 'file')} changed")
        return "Done · " + ", ".join(parts)

    def _elapsed(self) -> str:
        if self._started_at is None:
            return "0.0s"
        seconds = max((datetime.now(self._started_at.tzinfo) - self._started_at).total_seconds(), 0)
        return self._format_duration(seconds)

    def _columns(self) -> int:
        with suppress(ValueError):
            columns = int(os.environ.get("COLUMNS", ""))
            if columns > 0:
                return columns
        with suppress(AttributeError, OSError, ValueError):
            columns = os.get_terminal_size(self._stream.fileno()).columns
            if columns > 0:
                return columns
        return 80

    def _is_interactive(self) -> bool:
        with suppress(AttributeError):
            return bool(self._stream.isatty() and os.environ.get("TERM") != "dumb")
        return False

    @classmethod
    def _warning_label(cls, event: TraceEvent) -> str:
        if event.kind == "result.rejected":
            return "Result did not match the contract, retrying"
        tool = event.data.get("tool") or "Step"
        outcome = event.kind.rsplit(".", 1)[-1]
        detail = cls._detail(event.data.get("reason") or event.data.get("error"))
        return f"{tool} {outcome}: {detail}" if detail else f"{tool} {outcome}"

    @staticmethod
    def _answer_label(event: TraceEvent) -> str:
        if event.data.get("reason") == "question_limit":
            return "Question limit reached; agent decides"
        if event.data.get("delegated"):
            return "Decision delegated to agent"
        return "Answer received"

    @classmethod
    def _detail(cls, value: object) -> str:
        return cls._shorten(cls._first_line(value), cls._detail_width)

    @staticmethod
    def _first_line(value: object) -> str:
        if value is None:
            return ""
        for line in str(value).splitlines():
            if line.strip():
                return " ".join(line.split())
        return ""

    @staticmethod
    def _shorten(text: str, width: int) -> str:
        if len(text) <= width:
            return text
        return text[: max(width - 1, 0)].rstrip() + "…"

    @staticmethod
    def _count(value: int, noun: str) -> str:
        return f"{value} {noun}" if value == 1 else f"{value} {noun}s"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes, secs = divmod(int(seconds), 60)
        if minutes < 60:
            return f"{minutes}m {secs:02d}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes:02d}m"
