from datetime import UTC, datetime
from io import StringIO

import pytest

from pilota import FinalResult, ScriptedModel, TerminalProgress, TraceEvent, run_agent


class TerminalStream(StringIO):
    def isatty(self) -> bool:
        return True


def event(kind: str, data: dict[str, object] | None = None) -> TraceEvent:
    return TraceEvent(kind, data or {}, datetime.now(UTC))


def test_progress_callback_receives_live_trace_events() -> None:
    events: list[TraceEvent] = []

    execution = run_agent(
        "Return five",
        model=ScriptedModel([FinalResult(5)]),
        returns=int,
        progress=events.append,
    )

    assert events == list(execution.trace.events)
    assert [item.kind for item in events] == [
        "execution.started",
        "model.requested",
        "model.responded",
        "result.produced",
        "execution.completed",
    ]


def test_terminal_progress_uses_plain_lines_for_non_tty_streams() -> None:
    stream = StringIO()
    progress = TerminalProgress(stream)

    progress(event("execution.started"))
    progress(event("model.requested", {"call": 1}))
    progress(event("model.responded", {"call": 1}))
    progress(event("execution.completed"))

    output = stream.getvalue()
    assert "\033[" not in output
    assert "[pilota] Starting agent" in output
    assert "[pilota] Thinking · model call 1" in output
    assert "[pilota] Model call 1 finished" in output
    assert "[pilota] Done" in output


def test_terminal_progress_renders_colored_live_status_in_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)
    stream = TerminalStream()
    progress = TerminalProgress(stream, refresh_interval=60)

    progress(event("execution.started"))
    progress(event("model.requested", {"call": 1}))
    progress(event("model.responded", {"call": 1}))
    progress(event("execution.completed"))

    output = stream.getvalue()
    assert "\r\033[2K" in output
    assert "\033[36m" in output
    assert "Thinking · model call 1" in output
    assert "\033[32m✓\033[0m Done" in output
    assert output.endswith("\n")


def test_terminal_progress_stops_spinner_before_human_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")
    stream = TerminalStream()
    progress = TerminalProgress(stream, refresh_interval=60)

    progress(event("execution.started"))
    progress(event("tool.started", {"tool": "ask_human"}))
    progress(event("human.question", {"text": "Choose one", "options": []}))

    assert "Waiting for input" in stream.getvalue()
    assert stream.getvalue().endswith("\n")


def test_terminal_progress_rejects_invalid_refresh_interval() -> None:
    with pytest.raises(ValueError, match="refresh_interval"):
        TerminalProgress(refresh_interval=0)
