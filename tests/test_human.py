from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from pilota import (
    Answer,
    AskHuman,
    DirectoryWorkspace,
    FinalResult,
    InMemoryWorkspace,
    NoHuman,
    Question,
    ScriptedModel,
    TerminalHuman,
    ToolCall,
    agent,
    run_agent,
)


class FakeHuman:
    def __init__(self, *answers: Answer) -> None:
        self.answers = list(answers)
        self.questions: list[Question] = []

    def ask(self, question: Question) -> Answer:
        self.questions.append(question)
        return self.answers.pop(0)


def test_terminal_human_selects_one_option() -> None:
    human = TerminalHuman(input=StringIO("2\n"), output=StringIO())

    assert human.ask(Question("Choose one", options=("first", "second"))) == Answer(
        choices=("second",)
    )


def test_terminal_human_selects_multiple_options_in_order() -> None:
    human = TerminalHuman(input=StringIO("1, 3 1\n"), output=StringIO())

    assert human.ask(
        Question("Choose any", options=("first", "second", "third"), multiple=True)
    ) == Answer(choices=("first", "third"))


def test_terminal_human_can_delegate_from_options() -> None:
    human = TerminalHuman(input=StringIO("0\n"), output=StringIO())

    assert human.ask(Question("Choose one", options=("first",))) == Answer(delegated=True)


def test_terminal_human_reprompts_after_invalid_number() -> None:
    output = StringIO()
    human = TerminalHuman(input=StringIO("9\n2\n"), output=output)

    assert human.ask(Question("Choose one", options=("first", "second"))) == Answer(
        choices=("second",)
    )
    assert "out of range" in output.getvalue()
    assert output.getvalue().count("> ") == 2


def test_terminal_human_accepts_other_text_with_options() -> None:
    human = TerminalHuman(input=StringIO("Not sure yet\n"), output=StringIO())

    assert human.ask(Question("Choose one", options=("first",))) == Answer(text="Not sure yet")


def test_terminal_human_accepts_free_text_without_options() -> None:
    human = TerminalHuman(input=StringIO("  A short answer  \n"), output=StringIO())

    assert human.ask(Question("What do you think?")) == Answer(text="A short answer")


def test_terminal_human_empty_free_text_delegates() -> None:
    human = TerminalHuman(input=StringIO("   \n"), output=StringIO())

    assert human.ask(Question("What do you think?")) == Answer(delegated=True)


def test_terminal_human_eof_delegates() -> None:
    human = TerminalHuman(input=StringIO(""), output=StringIO())

    assert human.ask(Question("What do you think?")) == Answer(delegated=True)


def test_terminal_human_renders_question_context() -> None:
    output = StringIO()
    human = TerminalHuman(input=StringIO("1\n"), output=output)
    attachment = Path("variant.html")

    human.ask(
        Question(
            "Who will use the dashboard?",
            options=("staff", "customers"),
            why="helps choose interface density",
            attachments=(attachment,),
        )
    )

    rendered = output.getvalue()
    assert "? Who will use the dashboard?" in rendered
    assert "(helps choose interface density)" in rendered
    assert "Attachments:" in rendered
    assert str(attachment.resolve()) in rendered
    assert "1) staff" in rendered
    assert "2) customers" in rendered


@pytest.mark.parametrize(
    ("text", "options", "multiple"),
    [
        ("", (), False),
        ("  ", (), False),
        ("Choose", (), True),
    ],
)
def test_question_validation(
    text: str,
    options: tuple[str, ...],
    multiple: bool,
) -> None:
    with pytest.raises(ValueError):
        Question(text, options=options, multiple=multiple)


def test_no_human_delegates() -> None:
    assert NoHuman().ask(Question("Choose")) == Answer(delegated=True)


def test_agent_can_ask_human() -> None:
    human = FakeHuman(Answer(choices=("staff",)))
    model = ScriptedModel(
        [
            ToolCall(
                id="ask",
                name="ask_human",
                arguments={"text": "Who will use this?", "options": ["staff", "customers"]},
            ),
            FinalResult("Built for staff"),
        ]
    )

    assert (
        agent(
            "Build a dashboard",
            model=model,
            returns=str,
            tools=[AskHuman(human)],
        )
        == "Built for staff"
    )
    assert human.questions == [Question("Who will use this?", options=("staff", "customers"))]


def test_ask_human_returns_observation_and_trace_events() -> None:
    model = ScriptedModel(
        [
            ToolCall(
                id="ask",
                name="ask_human",
                arguments={"text": "Who will use this?", "options": ["staff", "customers"]},
            ),
            FinalResult("Built for staff"),
        ]
    )
    execution = run_agent(
        "Build a dashboard",
        model=model,
        returns=str,
        tools=[AskHuman(FakeHuman(Answer(choices=("staff",))))],
    )

    assert model.requests[1].observations[0].output == {
        "choices": ["staff"],
        "text": None,
        "delegated": False,
    }
    events = {
        event.kind: event.data
        for event in execution.trace.events
        if event.kind.startswith("human.")
    }
    assert events == {
        "human.question": {"text": "Who will use this?", "options": ["staff", "customers"]},
        "human.answer": {"choices": ["staff"], "text": None, "delegated": False},
    }


def test_ask_human_question_budget_is_per_execution() -> None:
    human = FakeHuman(Answer(text="First answer"))
    ask_human = AskHuman(human, max_questions=1)
    model = ScriptedModel(
        [
            ToolCall("first", "ask_human", {"text": "First?"}),
            ToolCall("second", "ask_human", {"text": "Second?"}),
            FinalResult("Done"),
        ]
    )

    execution = run_agent("Ask twice", model=model, returns=str, tools=[ask_human])

    assert len(human.questions) == 1
    assert model.requests[1].observations[0].output == {
        "choices": [],
        "text": "First answer",
        "delegated": False,
    }
    assert model.requests[2].observations[1].output == {
        "choices": [],
        "text": None,
        "delegated": True,
        "note": "Question limit reached; decide yourself.",
    }
    limit_answer = next(
        event.data
        for event in execution.trace.events
        if event.kind == "human.answer" and event.data.get("reason") == "question_limit"
    )
    assert limit_answer == {
        "choices": [],
        "text": None,
        "delegated": True,
        "reason": "question_limit",
    }
    assert len([event for event in execution.trace.events if event.kind == "human.question"]) == 1


def test_invalid_ask_human_arguments_are_tool_failures() -> None:
    model = ScriptedModel(
        [
            ToolCall("ask", "ask_human", {"text": ""}),
            FinalResult("Done"),
        ]
    )

    execution = run_agent(
        "Ask an invalid question",
        model=model,
        returns=str,
        tools=[AskHuman(FakeHuman())],
    )

    assert "non-empty string" in model.requests[1].observations[0].error
    assert "tool.failed" in [event.kind for event in execution.trace.events]


def test_ask_human_attachment_from_directory_workspace(tmp_path: Path) -> None:
    attachment = tmp_path / "preview.html"
    attachment.write_text("<h1>Preview</h1>")
    workspace = DirectoryWorkspace(tmp_path, allow={"execute"})
    human = FakeHuman(Answer(text="Use the first layout"))
    model = ScriptedModel(
        [
            ToolCall(
                "ask",
                "ask_human",
                {"text": "Which layout?", "attachments": ["preview.html"]},
            ),
            FinalResult("Done"),
        ]
    )

    run_agent(
        "Choose a layout",
        model=model,
        returns=str,
        tools=[AskHuman(human)],
        workspace=workspace,
    )

    assert human.questions[0].attachments == (attachment.resolve(),)


def test_ask_human_missing_attachment_is_a_tool_failure(tmp_path: Path) -> None:
    model = ScriptedModel(
        [
            ToolCall(
                "ask",
                "ask_human",
                {"text": "Which layout?", "attachments": ["missing.html"]},
            ),
            FinalResult("Done"),
        ]
    )
    execution = run_agent(
        "Choose a layout",
        model=model,
        returns=str,
        tools=[AskHuman(FakeHuman())],
        workspace=DirectoryWorkspace(tmp_path, allow={"execute"}),
    )

    assert "not an existing file" in model.requests[1].observations[0].error
    assert "tool.failed" in [event.kind for event in execution.trace.events]


def test_ask_human_rejects_attachment_path_escape(tmp_path: Path) -> None:
    model = ScriptedModel(
        [
            ToolCall(
                "ask",
                "ask_human",
                {"text": "Which layout?", "attachments": ["../outside.html"]},
            ),
            FinalResult("Done"),
        ]
    )
    execution = run_agent(
        "Choose a layout",
        model=model,
        returns=str,
        tools=[AskHuman(FakeHuman())],
        workspace=DirectoryWorkspace(tmp_path, allow={"execute"}),
    )

    assert "Invalid AskHuman attachment path" in model.requests[1].observations[0].error
    assert "tool.failed" in [event.kind for event in execution.trace.events]


def test_ask_human_rejects_in_memory_workspace_attachments() -> None:
    model = ScriptedModel(
        [
            ToolCall("ask", "ask_human", {"text": "Which?", "attachments": ["preview.html"]}),
            FinalResult("Done"),
        ]
    )
    execution = run_agent(
        "Choose a layout",
        model=model,
        returns=str,
        tools=[AskHuman(FakeHuman())],
        workspace=InMemoryWorkspace({"preview.html": "<h1>Preview</h1>"}),
    )

    assert "process-backed workspace" in model.requests[1].observations[0].error
    assert "tool.failed" in [event.kind for event in execution.trace.events]


def test_ask_human_rejects_negative_question_budget() -> None:
    with pytest.raises(ValueError, match="max_questions"):
        AskHuman(FakeHuman(), max_questions=-1)
