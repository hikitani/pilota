from __future__ import annotations

from pathlib import Path

import pytest

from pilota import FinalResult, InstructionFile, ScriptedModel, ToolCall, agent
from pilota.errors import ConfigurationError


class CountingInstruction:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    def render(self) -> str:
        self.calls += 1
        return self.content


class InvalidInstruction:
    def render(self) -> str:
        return 42  # type: ignore[return-value]


def test_instruction_file_content_is_sent_to_model(tmp_path: Path) -> None:
    instruction_path = tmp_path / "python.md"
    instruction_path.write_text("Use type annotations.\n")
    model = ScriptedModel([FinalResult("done")])

    result = agent(
        "Apply the instruction",
        model=model,
        instructions=[InstructionFile(instruction_path)],
        returns=str,
    )

    assert result == "done"
    assert model.requests[0].instructions == ("Use type annotations.\n",)


def test_plain_instruction_string_is_never_treated_as_a_path(tmp_path: Path) -> None:
    instruction_path = tmp_path / "secret.md"
    instruction_path.write_text("file contents must not be loaded")
    literal = str(instruction_path)
    model = ScriptedModel([FinalResult("done")])

    agent(
        "Use a literal instruction",
        model=model,
        instructions=[literal],
        returns=str,
    )

    assert model.requests[0].instructions == (literal,)


def test_instruction_is_rendered_once_for_all_model_turns() -> None:
    instruction = CountingInstruction("Keep the result concise.")
    model = ScriptedModel(
        [
            ToolCall(id="missing", name="missing", arguments={}),
            FinalResult("done"),
        ]
    )

    agent(
        "Use two model turns",
        model=model,
        instructions=[instruction],
        returns=str,
    )

    assert instruction.calls == 1
    assert len(model.requests) == 2
    assert model.requests[0].instructions == model.requests[1].instructions


def test_missing_instruction_file_stops_before_model_call(tmp_path: Path) -> None:
    model = ScriptedModel([FinalResult("unused")])

    with pytest.raises(ConfigurationError, match="Could not load instruction file") as raised:
        agent(
            "Do not call the model",
            model=model,
            instructions=[InstructionFile(tmp_path / "missing.md")],
            returns=str,
        )

    assert model.requests == []
    assert raised.value.execution_id is not None


def test_instruction_must_render_text() -> None:
    model = ScriptedModel([FinalResult("unused")])

    with pytest.raises(ConfigurationError, match="expected str"):
        agent(
            "Reject invalid instruction output",
            model=model,
            instructions=[InvalidInstruction()],
            returns=str,
        )

    assert model.requests == []
