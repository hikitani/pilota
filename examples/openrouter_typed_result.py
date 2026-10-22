"""Return a typed plan through OpenRouter structured outputs."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from pilota import agent
from pilota.providers.openrouter import OpenRouterModel


@dataclass(frozen=True)
class Plan:
    steps: list[str]
    risks: list[str]


def main() -> None:
    model_name = os.environ["OPENROUTER_MODEL"]

    with OpenRouterModel(model_name) as model:
        plan = agent(
            "Create a short implementation plan",
            model=model,
            context={
                "task": "Add response caching to a Python HTTP client",
                "constraints": ["Preserve the public API", "Include tests"],
            },
            returns=Plan,
        )

    print(json.dumps(asdict(plan), indent=2))


if __name__ == "__main__":
    main()
