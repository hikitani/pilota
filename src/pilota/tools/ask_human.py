"""Ask a human for information missing from an agent task."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from threading import Lock
from typing import Any

from pilota.errors import PermissionDenied, ToolError
from pilota.human import Answer, Human, Question
from pilota.models import ToolSpec
from pilota.tools.base import ProcessWorkspaceHandle, ToolContext


class AskHuman:
    """Expose a bounded question channel to an agent."""

    def __init__(self, human: Human, *, max_questions: int = 5) -> None:
        if max_questions < 0:
            raise ValueError("max_questions cannot be negative")
        self._human = human
        self._max_questions = max_questions
        self._questions_by_execution: dict[str, int] = {}
        self._lock = Lock()

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ask_human",
            description=(
                "Ask the human only when information is genuinely missing. Use plain, "
                "non-expert language and prefer offering options. The human may delegate; "
                "if they do, decide yourself and state your assumption in your result."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "multiple": {"type": "boolean"},
                    "why": {"type": "string"},
                    "attachments": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        )

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> dict[str, Any]:
        question = self._question_from_arguments(arguments, context)

        with self._lock:
            asked = self._questions_by_execution.get(context.execution_id, 0)
            if asked >= self._max_questions:
                answer_data: dict[str, Any] = {
                    "choices": [],
                    "text": None,
                    "delegated": True,
                    "reason": "question_limit",
                }
                context.record("human.answer", answer_data)
                return {
                    "choices": [],
                    "text": None,
                    "delegated": True,
                    "note": "Question limit reached; decide yourself.",
                }
            self._questions_by_execution[context.execution_id] = asked + 1

        context.record(
            "human.question",
            {"text": question.text, "options": list(question.options)},
        )
        answer = self._human.ask(question)
        if not isinstance(answer, Answer):
            raise ToolError("Human.ask must return an Answer")
        answer_data = {
            "choices": list(answer.choices),
            "text": answer.text,
            "delegated": answer.delegated,
        }
        context.record("human.answer", answer_data)
        return answer_data

    def _question_from_arguments(
        self,
        arguments: Mapping[str, Any],
        context: ToolContext,
    ) -> Question:
        if not isinstance(arguments, Mapping):
            raise ToolError("AskHuman arguments must be an object")
        allowed = {"text", "options", "multiple", "why", "attachments"}
        extra = arguments.keys() - allowed
        if extra:
            raise ToolError(f"Unexpected AskHuman argument: {next(iter(extra))!r}")

        text = arguments.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ToolError("AskHuman text must be a non-empty string")

        options = arguments.get("options", [])
        if not isinstance(options, list) or not all(isinstance(item, str) for item in options):
            raise ToolError("AskHuman options must be a list of strings")

        multiple = arguments.get("multiple", False)
        if not isinstance(multiple, bool):
            raise ToolError("AskHuman multiple must be a boolean")

        why = arguments.get("why")
        if why is not None and not isinstance(why, str):
            raise ToolError("AskHuman why must be a string")

        raw_attachments = arguments.get("attachments", [])
        if not isinstance(raw_attachments, list) or not all(
            isinstance(item, str) for item in raw_attachments
        ):
            raise ToolError("AskHuman attachments must be a list of paths")
        attachments = self._resolve_attachments(raw_attachments, context)

        try:
            return Question(
                text=text,
                options=tuple(options),
                multiple=multiple,
                why=why,
                attachments=attachments,
            )
        except ValueError as error:
            raise ToolError(str(error), execution_id=context.execution_id) from error

    @staticmethod
    def _resolve_attachments(
        paths: list[str],
        context: ToolContext,
    ) -> tuple[Path, ...]:
        if not paths:
            return ()
        if context.workspace is None:
            raise ToolError(
                "AskHuman attachments require a process-backed workspace",
                execution_id=context.execution_id,
            )
        if not isinstance(context.workspace, ProcessWorkspaceHandle):
            raise ToolError(
                "AskHuman attachments require a process-backed workspace",
                execution_id=context.execution_id,
            )

        resolved: list[Path] = []
        for value in paths:
            relative = Path(value)
            if relative.is_absolute() or ".." in relative.parts or not relative.name:
                raise ToolError(
                    f"Invalid AskHuman attachment path: {value}",
                    execution_id=context.execution_id,
                )
            parent = str(relative.parent)
            try:
                directory = context.workspace.execution_directory(parent)
                attachment = (directory / relative.name).resolve()
                if not attachment.is_relative_to(directory.resolve()):
                    raise ToolError(
                        f"AskHuman attachment escapes the workspace: {value}",
                        execution_id=context.execution_id,
                    )
                if not attachment.is_file():
                    raise ToolError(
                        f"AskHuman attachment is not an existing file: {value}",
                        execution_id=context.execution_id,
                    )
            except ToolError:
                raise
            except (OSError, PermissionDenied, ValueError) as error:
                raise ToolError(
                    f"Cannot resolve AskHuman attachment {value!r}: {error}",
                    execution_id=context.execution_id,
                ) from error
            resolved.append(attachment)
        return tuple(resolved)
