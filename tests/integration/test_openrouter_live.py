import os
from dataclasses import dataclass

import pytest

from pilota import Editor, InMemoryWorkspace, agent
from pilota.providers.openrouter import OpenRouterModel

RUN_LIVE = os.environ.get("PILOTA_RUN_OPENROUTER_TESTS") == "1"
API_KEY = os.environ.get("OPENROUTER_API_KEY")
MODEL = os.environ.get("OPENROUTER_MODEL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (RUN_LIVE and API_KEY and MODEL),
        reason=(
            "Set PILOTA_RUN_OPENROUTER_TESTS=1, OPENROUTER_API_KEY, and OPENROUTER_MODEL "
            "to run live OpenRouter tests"
        ),
    ),
]


@dataclass(frozen=True)
class Answer:
    value: int


@dataclass(frozen=True)
class Change:
    summary: str


def test_openrouter_live_structured_result() -> None:
    with OpenRouterModel(MODEL or "", api_key=API_KEY) as model:
        result = agent(
            "Return the integer produced by adding two and three.",
            model=model,
            returns=Answer,
        )

    assert result == Answer(value=5)


def test_openrouter_live_tool_call() -> None:
    workspace = InMemoryWorkspace()

    with OpenRouterModel(MODEL or "", api_key=API_KEY) as model:
        result = agent(
            "Use the editor tool to write exactly 'ready\\n' to status.txt, "
            "then summarize the change.",
            model=model,
            tools=[Editor()],
            workspace=workspace,
            returns=Change,
        )

    assert workspace.read_text("status.txt") == "ready\n"
    assert result.summary
