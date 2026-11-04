from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from threading import Event

import pytest

from pilota import (
    Answer,
    AskHuman,
    FinalResult,
    Journal,
    Question,
    ScriptedModel,
    TerminalHuman,
    ToolCall,
    agent,
    run_agent,
)
from pilota.errors import JournalError, ProviderError
from pilota.models import ModelRequest


@dataclass(frozen=True)
class Result:
    message: str
    path: Path


class FakeHuman:
    def __init__(self, *answers: Answer) -> None:
        self.answers = list(answers)
        self.questions: list[Question] = []

    def ask(self, question: Question) -> Answer:
        self.questions.append(question)
        return self.answers.pop(0)


class BlockingModel:
    def __init__(self, started: Event, release: Event, value: str) -> None:
        self._started = started
        self._release = release
        self._value = value

    def respond(self, request: ModelRequest) -> FinalResult:
        del request
        self._started.set()
        assert self._release.wait(timeout=5)
        return FinalResult(self._value)


def test_successful_agent_is_replayed_without_calling_model(tmp_path: Path) -> None:
    journal_path = tmp_path / "run.jsonl"
    first_model = ScriptedModel([FinalResult({"message": "done", "path": "result.txt"})])

    with Journal(journal_path):
        first = run_agent("Build it", model=first_model, returns=Result)

    events = []
    replay_model = ScriptedModel([])
    with Journal(journal_path):
        replayed = run_agent(
            "Build it",
            model=replay_model,
            returns=Result,
            progress=events.append,
        )

    assert replayed.value == first.value == Result("done", Path("result.txt"))
    assert replayed.usage.model_calls == 0
    assert replay_model.requests == []
    assert [event.kind for event in events] == [
        "execution.started",
        "journal.replayed",
        "result.produced",
        "execution.completed",
    ]


def test_failed_agent_is_not_recorded(tmp_path: Path) -> None:
    journal_path = tmp_path / "run.jsonl"

    with pytest.raises(ProviderError), Journal(journal_path):
        agent("Build it", model=ScriptedModel([]), returns=str)

    assert not journal_path.exists()

    with Journal(journal_path):
        assert agent("Build it", model=ScriptedModel([FinalResult("done")]), returns=str) == "done"

    replay_model = ScriptedModel([])
    with Journal(journal_path):
        assert agent("Build it", model=replay_model, returns=str) == "done"
    assert replay_model.requests == []


def test_changed_call_archives_old_tail_and_replaces_active_branch(tmp_path: Path) -> None:
    journal_path = tmp_path / "run.jsonl"

    with Journal(journal_path):
        assert agent("A", model=ScriptedModel([FinalResult("a")]), returns=str) == "a"
        assert agent("B", model=ScriptedModel([FinalResult("old")]), returns=str) == "old"

    progress = []
    with Journal(journal_path):
        assert agent("A", model=ScriptedModel([]), returns=str) == "a"
        assert (
            agent(
                "B changed",
                model=ScriptedModel([FinalResult("new")]),
                returns=str,
                progress=progress.append,
            )
            == "new"
        )

    assert any(event.kind == "journal.replay_completed" for event in progress)
    assert len(list(tmp_path.glob("run.jsonl.archive-*"))) == 1

    first_model = ScriptedModel([])
    second_model = ScriptedModel([])
    with Journal(journal_path):
        assert agent("A", model=first_model, returns=str) == "a"
        assert agent("B changed", model=second_model, returns=str) == "new"
    assert first_model.requests == []
    assert second_model.requests == []


def test_human_answer_survives_failed_agent(tmp_path: Path) -> None:
    journal_path = tmp_path / "run.jsonl"
    first_human = FakeHuman(Answer(choices=("staff",)))
    failing_model = ScriptedModel(
        [
            ToolCall(
                "ask",
                "ask_human",
                {"text": "Who will use this?", "options": ["staff", "customers"]},
            )
        ]
    )

    with pytest.raises(ProviderError), Journal(journal_path):
        agent(
            "Build a dashboard",
            model=failing_model,
            returns=str,
            tools=[AskHuman(first_human)],
        )

    assert len(first_human.questions) == 1

    replay_human = FakeHuman()
    recovering_model = ScriptedModel(
        [
            ToolCall(
                "ask",
                "ask_human",
                {"text": "Who will use this?", "options": ["staff", "customers"]},
            ),
            FinalResult("Built for staff"),
        ]
    )
    summary_model = ScriptedModel([FinalResult("Summary")])
    with Journal(journal_path):
        assert (
            agent(
                "Build a dashboard",
                model=recovering_model,
                returns=str,
                tools=[AskHuman(replay_human)],
            )
            == "Built for staff"
        )
        assert agent("Summarize", model=summary_model, returns=str) == "Summary"

    assert replay_human.questions == []
    assert recovering_model.requests[1].observations[0].output == {
        "choices": ["staff"],
        "text": None,
        "delegated": False,
    }

    final_model = ScriptedModel([])
    final_summary_model = ScriptedModel([])
    with Journal(journal_path):
        assert (
            agent(
                "Build a dashboard",
                model=final_model,
                returns=str,
                tools=[AskHuman(FakeHuman())],
            )
            == "Built for staff"
        )
        assert agent("Summarize", model=final_summary_model, returns=str) == "Summary"
    assert final_model.requests == []
    assert final_summary_model.requests == []


def test_direct_terminal_human_answer_is_replayed(tmp_path: Path) -> None:
    journal_path = tmp_path / "run.jsonl"
    question = Question("Choose", options=("first", "second"))

    with Journal(journal_path):
        assert TerminalHuman(StringIO("2\n"), StringIO()).ask(question) == Answer(
            choices=("second",)
        )

    output = StringIO()
    with Journal(journal_path):
        assert TerminalHuman(StringIO(""), output).ask(question) == Answer(choices=("second",))
    assert output.getvalue() == ""


def test_sensitive_human_answer_is_not_recorded(tmp_path: Path) -> None:
    journal_path = tmp_path / "run.jsonl"
    question = Question("API key?", sensitive=True)

    with Journal(journal_path):
        assert TerminalHuman(StringIO("first\n"), StringIO()).ask(question) == Answer(text="first")
    with Journal(journal_path):
        assert TerminalHuman(StringIO("second\n"), StringIO()).ask(question) == Answer(
            text="second"
        )

    assert not journal_path.exists()


def test_only_one_journal_can_be_active(tmp_path: Path) -> None:
    with (
        Journal(tmp_path / "first.jsonl"),
        pytest.raises(JournalError, match="Only one Journal"),
        Journal(tmp_path / "second.jsonl"),
    ):
        pass


def test_incomplete_last_line_is_ignored(tmp_path: Path) -> None:
    journal_path = tmp_path / "run.jsonl"
    journal_path.write_text(
        json.dumps(
            {
                "version": 1,
                "sequence": 0,
                "parent": None,
                "kind": "agent",
                "fingerprint": "sha256:" + ("0" * 64),
                "data": {"value": "stale", "artifacts": []},
            }
        )
        + "\n"
        + '{"version":',
        encoding="utf-8",
    )

    with Journal(journal_path):
        assert agent("Fresh", model=ScriptedModel([FinalResult("new")]), returns=str) == "new"

    assert len(list(tmp_path.glob("run.jsonl.archive-*"))) == 1


def test_parallel_agents_can_finish_out_of_order_and_replay_in_call_order(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "run.jsonl"
    first_started = Event()
    second_started = Event()
    release_first = Event()
    release_second = Event()

    with Journal(journal_path), ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            agent,
            "First",
            model=BlockingModel(first_started, release_first, "first"),
            returns=str,
        )
        assert first_started.wait(timeout=5)
        second = executor.submit(
            agent,
            "Second",
            model=BlockingModel(second_started, release_second, "second"),
            returns=str,
        )
        assert second_started.wait(timeout=5)
        release_second.set()
        assert second.result(timeout=5) == "second"
        release_first.set()
        assert first.result(timeout=5) == "first"

    replay_started = Event()
    replay_release = Event()
    first_replay = BlockingModel(replay_started, replay_release, "unused")
    second_replay = BlockingModel(replay_started, replay_release, "unused")
    with Journal(journal_path):
        assert agent("First", model=first_replay, returns=str) == "first"
        assert agent("Second", model=second_replay, returns=str) == "second"
    assert not replay_started.is_set()
