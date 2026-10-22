"""Explicit reusable instruction inputs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeAlias

from pilota.errors import AgentError, ConfigurationError


class Instruction(Protocol):
    def render(self) -> str: ...


InstructionInput: TypeAlias = str | Instruction


@dataclass(frozen=True)
class InstructionFile:
    path: str | Path
    encoding: str = "utf-8"

    def render(self) -> str:
        try:
            return Path(self.path).read_text(encoding=self.encoding)
        except (LookupError, OSError, UnicodeError) as error:
            raise ConfigurationError(
                f"Could not load instruction file {self.path!s}: {error}"
            ) from error


def render_instructions(
    instructions: Sequence[InstructionInput],
    *,
    execution_id: str,
) -> tuple[str, ...]:
    rendered: list[str] = []
    for index, instruction in enumerate(instructions):
        if isinstance(instruction, str):
            rendered.append(instruction)
            continue

        try:
            content = instruction.render()
        except AgentError as error:
            raise ConfigurationError(
                str(error),
                execution_id=execution_id,
            ) from error
        except Exception as error:
            raise ConfigurationError(
                f"Instruction {index} could not be rendered: {error}",
                execution_id=execution_id,
            ) from error

        if not isinstance(content, str):
            raise ConfigurationError(
                f"Instruction {index} rendered {type(content).__name__}, expected str",
                execution_id=execution_id,
            )
        rendered.append(content)

    return tuple(rendered)
