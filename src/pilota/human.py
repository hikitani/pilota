"""Human input contracts and terminal implementations."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO


@dataclass(frozen=True)
class Question:
    """A question presented to a human."""

    text: str
    options: tuple[str, ...] = ()
    multiple: bool = False
    why: str | None = None
    attachments: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Question text must be non-empty")
        if self.multiple and not self.options:
            raise ValueError("Multiple selection requires options")


@dataclass(frozen=True)
class Answer:
    """A human's response to a question."""

    choices: tuple[str, ...] = ()
    text: str | None = None
    delegated: bool = False


class Human(Protocol):
    """A synchronous interface for asking a person a question."""

    def ask(self, question: Question) -> Answer: ...


class TerminalHuman:
    """Ask questions in a terminal and parse the human's response."""

    def __init__(
        self,
        input: TextIO | None = None,
        output: TextIO | None = None,
    ) -> None:
        self._input = input
        self._output = output

    def ask(self, question: Question) -> Answer:
        input_stream = self._input if self._input is not None else sys.stdin
        output_stream = self._output if self._output is not None else sys.stdout

        output_stream.write(f"? {question.text}\n")
        if question.why:
            output_stream.write(f"  ({question.why})\n")
        if question.attachments:
            output_stream.write("  Attachments:\n")
            for attachment in question.attachments:
                output_stream.write(f"    {attachment.resolve()}\n")
        if question.options:
            for index, option in enumerate(question.options, start=1):
                output_stream.write(f"  {index}) {option}\n")
            output_stream.write("  0) don't know, decide yourself\n")
        else:
            output_stream.write("  (empty answer: decide yourself)\n")

        while True:
            output_stream.write("> ")
            output_stream.flush()
            response = input_stream.readline()
            if response == "":
                return Answer(delegated=True)
            value = response.strip()

            if not question.options:
                if value:
                    return Answer(text=value)
                return Answer(delegated=True)

            if not value:
                output_stream.write("Please enter an option number or an answer.\n")
                continue
            if value == "0":
                return Answer(delegated=True)
            if all(
                character.isdecimal() or character.isspace() or character == ","
                for character in value
            ):
                tokens = _number_tokens(value)
                if (
                    not tokens
                    or any(not token.isdecimal() for token in tokens)
                    or (not question.multiple and len(tokens) != 1)
                ):
                    output_stream.write("Please enter valid option numbers.\n")
                    continue
                indexes = [int(token) for token in tokens]
                if any(index < 1 or index > len(question.options) for index in indexes):
                    output_stream.write("Option number is out of range.\n")
                    continue
                selected = tuple(
                    question.options[index - 1]
                    for position, index in enumerate(indexes)
                    if index not in indexes[:position]
                )
                return Answer(choices=selected)

            return Answer(text=value)


class NoHuman:
    """A human implementation that always delegates decisions to the agent."""

    def ask(self, question: Question) -> Answer:
        del question
        return Answer(delegated=True)


def _number_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    current = ""
    for character in value:
        if character.isdecimal():
            current += character
        elif current:
            tokens.append(current)
            current = ""
        elif character == ",":
            tokens.append("")
    if current:
        tokens.append(current)
    elif value.endswith(","):
        tokens.append("")
    return tokens
