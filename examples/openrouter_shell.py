"""Run one explicitly configured command through an OpenRouter agent."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from pilota import DirectoryWorkspace, Shell, agent
from pilota.providers.openrouter import OpenRouterModel


@dataclass(frozen=True)
class TestReport:
    summary: str
    passed: bool


def main() -> None:
    workspace = DirectoryWorkspace(
        Path.cwd(),
        allow={"list", "read", "execute"},
        deny_globs={".env", ".git/**"},
    )
    shell = Shell(
        {"tests": [sys.executable, "-m", "pytest"]},
        timeout=120,
    )

    with OpenRouterModel(os.environ["OPENROUTER_MODEL"]) as model:
        report = agent(
            "Run the test suite once and report whether it passed.",
            model=model,
            workspace=workspace,
            tools=[shell],
            returns=TestReport,
        )

    print(json.dumps(asdict(report), indent=2))


if __name__ == "__main__":
    main()
