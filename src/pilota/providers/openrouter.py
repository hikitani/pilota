"""OpenRouter chat-completions model adapter."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

import httpx
from pydantic_core import to_jsonable_python

from pilota.errors import ConfigurationError, ProviderError
from pilota.models import (
    RESULT_TOOL_NAME,
    FinalResult,
    ModelAction,
    ModelRequest,
    Observation,
    ToolCall,
    ToolSpec,
)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterModel:
    """Execute Pilota model requests through OpenRouter's Chat Completions API."""

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        http_referer: str | None = None,
        app_title: str | None = "Pilota",
        client: httpx.Client | None = None,
    ) -> None:
        selected_api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not selected_api_key:
            raise ConfigurationError(
                "OpenRouter requires api_key or the OPENROUTER_API_KEY environment variable"
            )
        if not model.strip():
            raise ConfigurationError("OpenRouter model must not be empty")

        self.model = model
        self._api_key = selected_api_key
        self._base_url = base_url.rstrip("/")
        self._http_referer = http_referer
        self._app_title = app_title
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def respond(self, request: ModelRequest) -> ModelAction:
        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(request),
            )
        except httpx.HTTPError as error:
            raise ProviderError(
                f"OpenRouter request failed: {error}",
                execution_id=request.execution_id,
            ) from error

        if not response.is_success:
            raise ProviderError(
                _error_message(response),
                execution_id=request.execution_id,
            )

        try:
            body = response.json()
        except ValueError as error:
            raise ProviderError(
                "OpenRouter returned a non-JSON response",
                execution_id=request.execution_id,
            ) from error

        return _parse_action(
            body,
            execution_id=request.execution_id,
            wrapped_result=request.result_schema.get("type") != "object",
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpenRouterModel:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._http_referer is not None:
            headers["HTTP-Referer"] = self._http_referer
        if self._app_title is not None:
            headers["X-OpenRouter-Title"] = self._app_title
        return headers

    def _payload(self, request: ModelRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": _messages(request),
            "tools": [
                *[_tool_payload(tool) for tool in request.tools],
                {
                    "type": "function",
                    "function": {
                        "name": RESULT_TOOL_NAME,
                        "description": "Submit the final result when the task is complete.",
                        "strict": True,
                        "parameters": _result_parameters(request.result_schema),
                    },
                },
            ],
            "tool_choice": "required",
            "parallel_tool_calls": False,
        }
        return payload


def _result_parameters(schema: Mapping[str, Any]) -> dict[str, Any]:
    if schema.get("type") != "object":
        value_schema = dict(schema)
        definitions = value_schema.pop("$defs", None)
        schema = {"type": "object", "properties": {"value": value_schema}, "required": ["value"]}
        if definitions is not None:
            schema["$defs"] = definitions
    return _strict_json_schema(schema)


def _messages(request: ModelRequest) -> list[dict[str, Any]]:
    if len(request.tool_calls) != len(request.observations):
        raise ConfigurationError(
            "Model request tool-call history is incomplete",
            execution_id=request.execution_id,
        )

    system_content = (
        "Execute one bounded task. Use only the supplied tools. "
        "When the task is complete, call final_result with the required result."
    )
    if request.instructions:
        system_content += "\n\nInstructions:\n" + "\n".join(
            f"- {instruction}" for instruction in request.instructions
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_content},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": request.task,
                    "context": to_jsonable_python(request.context),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]

    for tool_call, observation in zip(
        request.tool_calls,
        request.observations,
        strict=True,
    ):
        messages.extend(
            _tool_messages(
                tool_call, observation, wrapped_result=request.result_schema.get("type") != "object"
            )
        )

    return messages


def _tool_messages(
    tool_call: ToolCall, observation: Observation, *, wrapped_result: bool
) -> Sequence[dict[str, Any]]:
    if observation.call_id != tool_call.id or observation.tool_name != tool_call.name:
        raise ConfigurationError("Tool-call history does not match its observation")

    result: Any = (
        {"error": observation.error} if observation.error is not None else observation.output
    )

    return (
        {
            "role": "assistant",
            "content": tool_call.provider_data.get("content"),
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(
                            to_jsonable_python(
                                {"value": tool_call.arguments}
                                if wrapped_result and tool_call.name == RESULT_TOOL_NAME
                                else tool_call.arguments
                            ),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                }
            ],
            **{
                key: value
                for key, value in tool_call.provider_data.items()
                if key in {"reasoning", "reasoning_details"}
            },
        },
        {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.name,
            "content": json.dumps(
                to_jsonable_python(result),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    )


def _tool_payload(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": to_jsonable_python(tool.input_schema),
        },
    }


def _strict_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_schema_node(deepcopy(dict(schema)))
    if not isinstance(normalized, dict):
        raise ConfigurationError("Result schema must be a JSON object")
    return normalized


def _normalize_schema_node(value: Any) -> Any:
    if isinstance(value, dict):
        normalized = {
            key: _normalize_schema_node(item) for key, item in value.items() if key != "default"
        }
        properties = normalized.get("properties")
        if normalized.get("type") == "object" and isinstance(properties, dict):
            normalized.setdefault("additionalProperties", False)
            normalized["required"] = list(properties)
        return normalized
    if isinstance(value, list):
        return [_normalize_schema_node(item) for item in value]
    return value


def _parse_action(body: Any, *, execution_id: str, wrapped_result: bool = False) -> ModelAction:
    if not isinstance(body, Mapping):
        raise ProviderError("OpenRouter response must be a JSON object", execution_id=execution_id)

    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("OpenRouter response has no choices", execution_id=execution_id)

    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise ProviderError("OpenRouter choice must be an object", execution_id=execution_id)

    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        raise ProviderError("OpenRouter choice has no assistant message", execution_id=execution_id)

    tool_calls = message.get("tool_calls")
    if tool_calls:
        call = _parse_tool_call(tool_calls, message=message, execution_id=execution_id)
        if call.name == RESULT_TOOL_NAME:
            value = call.arguments
            if wrapped_result and isinstance(value, Mapping) and "value" in value:
                value = value["value"]
            return FinalResult(value, id=call.id, provider_data=call.provider_data)
        return call

    content = message.get("content")
    if isinstance(content, (Mapping, list)):
        return FinalResult(content)
    if not isinstance(content, str):
        raise ProviderError(
            "OpenRouter assistant message has no result content",
            execution_id=execution_id,
        )

    try:
        return FinalResult(json.loads(content))
    except json.JSONDecodeError:
        return FinalResult(content)


def _parse_tool_call(
    tool_calls: Any,
    *,
    message: Mapping[str, Any],
    execution_id: str,
) -> ToolCall:
    if not isinstance(tool_calls, list) or len(tool_calls) != 1:
        raise ProviderError(
            "Pilota currently requires exactly one OpenRouter tool call per model response",
            execution_id=execution_id,
        )

    raw_call = tool_calls[0]
    if not isinstance(raw_call, Mapping):
        raise ProviderError("OpenRouter tool call must be an object", execution_id=execution_id)

    call_id = raw_call.get("id")
    function = raw_call.get("function")
    if not isinstance(call_id, str) or not isinstance(function, Mapping):
        raise ProviderError("OpenRouter tool call is malformed", execution_id=execution_id)

    name = function.get("name")
    raw_arguments = function.get("arguments")
    if not isinstance(name, str) or not isinstance(raw_arguments, str):
        raise ProviderError("OpenRouter function call is malformed", execution_id=execution_id)

    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as error:
        raise ProviderError(
            "OpenRouter tool arguments are not valid JSON",
            execution_id=execution_id,
        ) from error
    if not isinstance(arguments, Mapping):
        raise ProviderError(
            "OpenRouter tool arguments must be a JSON object",
            execution_id=execution_id,
        )

    provider_data = {
        key: message[key] for key in ("content", "reasoning", "reasoning_details") if key in message
    }
    return ToolCall(
        id=call_id,
        name=name,
        arguments=arguments,
        provider_data=provider_data,
    )


def _error_message(response: httpx.Response) -> str:
    message = ""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, Mapping):
        error = body.get("error")
        if isinstance(error, Mapping) and isinstance(error.get("message"), str):
            message = error["message"].strip()
        elif isinstance(error, str):
            message = error.strip()

    prefix = f"OpenRouter request failed with HTTP {response.status_code}"
    return f"{prefix}: {message[:500]}" if message else prefix
