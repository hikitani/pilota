"""Let an OpenRouter model edit one explicitly confined directory."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from pilota import DirectoryWorkspace, Editor, agent
from pilota.providers.openrouter import OpenRouterModel


@dataclass(frozen=True)
class Change:
    summary: str
    files: list[Path]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "workspace",
        type=Path,
        help="Directory the agent may read and edit",
    )
    args = parser.parse_args()

    workspace = DirectoryWorkspace(
        args.workspace,
        allow={"list", "read", "create", "edit"},
        deny_globs={".env", ".git/**"},
    )
    model_name = os.environ["OPENROUTER_MODEL"]

    with OpenRouterModel(model_name) as model:
        change = agent(
            "Inspect the workspace and create NOTES.md with a concise description of its files.",
            model=model,
            workspace=workspace,
            tools=[Editor()],
            returns=Change,
        )

    print(json.dumps(asdict(change), default=str, indent=2))


if __name__ == "__main__":
    main()
