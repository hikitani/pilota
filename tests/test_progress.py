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
    assert "[pilota #1] Started" in output
    assert "[pilota #1] Thinking · model call 1" in output
    assert "[pilota #1] Model call 1 finished" in output
    assert "[pilota #1] Done · 1 model call" in output


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
    assert "\033[32m✓\033[0m #1 Done · 1 model call" in output
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


def test_terminal_progress_shows_journal_replay() -> None:
    stream = StringIO()
    progress = TerminalProgress(stream)

    progress(event("execution.started"))
    progress(event("journal.replayed", {"kind": "agent"}))
    progress(event("journal.replay_completed"))

    output = stream.getvalue()
    assert "[pilota #1] Replayed agent from journal" in output
    assert "[pilota #1] Journal replay complete; continuing live" in output


def test_terminal_progress_numbers_steps_and_shows_task_title() -> None:
    stream = StringIO()
    progress = TerminalProgress(stream)

    progress(event("execution.started", {"task": "\n    Analyze   the brief.\n    More text\n"}))
    progress(event("execution.completed"))
    progress(event("execution.started", {"task": "Propose directions"}))

    output = stream.getvalue()
    assert "[pilota #1] Started: Analyze the brief." in output
    assert "More text" not in output
    assert "[pilota #2] Started: Propose directions" in output


def test_terminal_progress_summarizes_completed_step() -> None:
    stream = StringIO()
    progress = TerminalProgress(stream)

    progress(event("execution.started", {"task": "Edit"}))
    for call in (1, 2):
        progress(event("model.requested", {"call": call}))
        progress(event("model.responded", {"call": call}))
    progress(event("tool.started", {"tool": "editor", "call_id": "a"}))
    progress(event("tool.completed", {"tool": "editor", "call_id": "a"}))
    progress(event("artifact.created", {"path": "a.txt"}))
    progress(event("artifact.modified", {"path": "b.txt"}))
    progress(event("execution.completed"))

    assert "[pilota #1] Done · 2 model calls, 1 tool call, 2 files changed" in stream.getvalue()


def test_terminal_progress_marks_journal_replayed_step() -> None:
    stream = StringIO()
    progress = TerminalProgress(stream)

    progress(event("execution.started", {"task": "Analyze"}))
    progress(event("journal.replayed", {"kind": "agent"}))
    progress(event("result.produced"))
    progress(event("execution.completed"))

    assert "[pilota #1] Done · replayed from journal" in stream.getvalue()


@pytest.mark.parametrize(
    ("terminal", "expected"),
    [
        (event("model.failed", {"error": "HTTP 503\ntraceback"}), "Model call failed: HTTP 503"),
        (
            event("execution.limit_exhausted", {"limit": "model_calls"}),
            "Model calls limit exhausted",
        ),
        (event("execution.cancelled", {"boundary": "after_model"}), "Cancelled after model"),
    ],
)
def test_terminal_progress_explains_how_step_ended(terminal: TraceEvent, expected: str) -> None:
    stream = StringIO()
    progress = TerminalProgress(stream)

    progress(event("execution.started", {"task": "Analyze"}))
    progress(event("model.requested", {"call": 1}))
    progress(terminal)

    output = stream.getvalue()
    assert f"[pilota #1] {expected}" in output
    assert "traceback" not in output


def test_terminal_progress_reports_only_first_terminal_event() -> None:
    stream = StringIO()
    progress = TerminalProgress(stream)

    progress(event("execution.started", {"task": "Analyze"}))
    progress(event("model.failed", {"error": "boom"}))
    progress(event("execution.limit_exhausted", {"limit": "wall_time"}))

    output = stream.getvalue()
    assert "Model call failed: boom" in output
    assert "limit exhausted" not in output


def test_terminal_progress_shows_tool_failure_reason() -> None:
    stream = StringIO()
    progress = TerminalProgress(stream)

    progress(event("execution.started"))
    progress(event("tool.failed", {"tool": "shell", "call_id": "a", "error": "exit 2"}))
    progress(event("tool.denied", {"tool": "editor", "reason": "read-only"}))

    output = stream.getvalue()
    assert "[pilota #1] shell failed: exit 2" in output
    assert "[pilota #1] editor denied: read-only" in output


def test_terminal_progress_shows_human_answer() -> None:
    stream = StringIO()
    progress = TerminalProgress(stream)

    progress(event("execution.started"))
    progress(event("human.question", {"text": "Pick", "options": []}))
    progress(event("human.answer", {"choices": ["a"], "text": None, "delegated": False}))
    progress(event("human.answer", {"choices": [], "text": None, "delegated": True}))
    progress(
        event(
            "human.answer",
            {"choices": [], "text": None, "delegated": True, "reason": "question_limit"},
        )
    )

    output = stream.getvalue()
    assert "Answer received" in output
    assert "Decision delegated to agent" in output
    assert "Question limit reached; agent decides" in output


def test_terminal_progress_keeps_live_line_within_terminal_width(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "40")
    stream = TerminalStream()
    progress = TerminalProgress(stream, refresh_interval=60)

    progress(event("execution.started", {"task": "Analyze this product before any visual work"}))
    progress(event("tool.started", {"tool": "a_tool_with_a_very_long_name_indeed"}))

    line = stream.getvalue().rsplit("\r\033[2K", 1)[-1]
    assert len(line) <= 39
    assert line.startswith("⠋ #1 Analyze")
    assert "…" in line
    assert line.rstrip().endswith("s")


def test_terminal_progress_formats_long_durations() -> None:
    assert TerminalProgress._format_duration(12.34) == "12.3s"
    assert TerminalProgress._format_duration(65) == "1m 05s"
    assert TerminalProgress._format_duration(3725) == "1h 02m"
