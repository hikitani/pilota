"""Human input contracts and terminal implementations."""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import local
from typing import Any, Protocol, TextIO

from pilota.errors import JournalError, ToolError
from pilota.journal import active_journal, fingerprint

_journal_state = local()


@dataclass(frozen=True)
class Question:
    """A question presented to a human."""

    text: str
    options: tuple[str, ...] = ()
    multiple: bool = False
    why: str | None = None
    attachments: tuple[Path, ...] = ()
    sensitive: bool = False

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
        return _journal_answer(question, lambda: self._ask_live(question))

    def _ask_live(self, question: Question) -> Answer:
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
                tokens = value.replace(",", " ").split()
                if not tokens or (not question.multiple and len(tokens) != 1):
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
        return _journal_answer(question, lambda: Answer(delegated=True))


def ask_human(
    human: Human,
    question: Question,
    *,
    record: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> Answer:
    """Ask any Human while honoring the active workflow journal."""

    def ask_live() -> Answer:
        _journal_state.bypass = True
        try:
            return human.ask(question)
        finally:
            _journal_state.bypass = False

    return _journal_answer(question, ask_live, record=record)


def _journal_answer(
    question: Question,
    ask_live: Callable[[], Answer],
    *,
    record: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> Answer:
    journal = active_journal()
    if journal is None or question.sensitive or getattr(_journal_state, "bypass", False):
        return _checked_answer(ask_live())

    question_fingerprint = fingerprint(
        {
            "text": question.text,
            "options": question.options,
            "multiple": question.multiple,
            "why": question.why,
            "attachments": [str(path) for path in question.attachments],
            "sensitive": question.sensitive,
        }
    )
    call = journal.begin("human", question_fingerprint)
    if call.replayed is not None:
        answer = _decode_answer(call.replayed)
        if record is not None:
            record("journal.replayed", {"kind": "human"})
        return answer
    if call.replay_ended and record is not None:
        record("journal.replay_completed", {"reason": "journal_exhausted_or_changed"})

    with journal.operation(call):
        answer = _checked_answer(ask_live())
    journal.complete(call, _encode_answer(answer))
    return answer


def _checked_answer(value: object) -> Answer:
    if not isinstance(value, Answer):
        raise ToolError("Human.ask must return an Answer")
    return value


def _encode_answer(answer: Answer) -> Mapping[str, Any]:
    return {
        "choices": list(answer.choices),
        "text": answer.text,
        "delegated": answer.delegated,
    }


def _decode_answer(value: Mapping[str, Any]) -> Answer:
    choices = value.get("choices")
    text = value.get("text")
    delegated = value.get("delegated")
    if (
        not isinstance(choices, list)
        or not all(isinstance(choice, str) for choice in choices)
        or (text is not None and not isinstance(text, str))
        or not isinstance(delegated, bool)
    ):
        raise JournalError("Journal human answer is invalid")
    return Answer(choices=tuple(choices), text=text, delegated=delegated)
