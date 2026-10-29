import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from pilota import Editor, InMemoryWorkspace, agent, run_agent
from pilota.errors import ConfigurationError, ProviderError
from pilota.models import ToolSpec
from pilota.providers.openrouter import OpenRouterModel, _result_parameters, _tool_payload


@dataclass(frozen=True)
class Change:
    summary: str
    files: list[Path]


@pytest.mark.parametrize("tool", [False, True])
def test_schema_refs_are_inlined(tool: bool) -> None:
    schema = {
        "type": "object",
        "$defs": {
            "Name": {"type": "string"},
            "Detail": {"type": "object", "properties": {"name": {"$ref": "#/$defs/Name"}}},
        },
        "properties": {"left": {"$ref": "#/$defs/Detail"}, "right": {"$ref": "#/$defs/Detail"}},
    }
    parameters = (
        _tool_payload(ToolSpec("test", "", schema))["function"]["parameters"]
        if tool
        else _result_parameters(schema)
    )
    assert "$ref" not in json.dumps(parameters)
    assert "$defs" not in json.dumps(parameters)
    assert parameters["properties"]["left"] == parameters["properties"]["right"]
    assert parameters["properties"]["left"]["properties"]["name"] == {"type": "string"}
    assert "$defs" in schema


def test_recursive_schema_retains_only_cyclic_definitions() -> None:
    schema = {
        "$ref": "#/$defs/Node",
        "$defs": {
            "Label": {"type": "string"},
            "Node": {
                "type": "object",
                "properties": {
                    "label": {"$ref": "#/$defs/Label"},
                    "children": {"type": "array", "items": {"$ref": "#/$defs/Node"}},
                },
            },
        },
    }
    parameters = _result_parameters(schema)
    assert set(parameters["$defs"]) == {"Node"}
    node = parameters["$defs"]["Node"]
    assert node["properties"]["label"] == {"type": "string"}
    assert node["properties"]["children"]["items"] == {"$ref": "#/$defs/Node"}


def test_openrouter_returns_a_typed_structured_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)

        assert request.url == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.headers["http-referer"] == "https://pilota.example"
        assert request.headers["x-openrouter-title"] == "Pilota tests"
        assert payload["model"] == "example/model"
        assert payload["messages"][1] == {
            "role": "user",
            "content": '{"task":"Plan caching","context":{"path":"src/cache.py"}}',
        }
        assert "response_format" not in payload
        function = payload["tools"][0]["function"]
        assert function["name"] == "final_result"
        assert function["strict"] is True
        assert function["parameters"]["type"] == "object"
        assert function["parameters"]["additionalProperties"] is False
        assert payload["tool_choice"] == "required"
        assert "parallel_tool_calls" not in payload

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "summary": "Planned response caching",
                                    "files": ["src/cache.py"],
                                }
                            ),
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = OpenRouterModel(
            "example/model",
            api_key="test-key",
            http_referer="https://pilota.example",
            app_title="Pilota tests",
            client=client,
        )

        result = agent(
            "Plan caching",
            context={"path": Path("src/cache.py")},
            model=model,
            returns=Change,
        )

    assert result == Change(
        summary="Planned response caching",
        files=[Path("src/cache.py")],
    )


def test_openrouter_round_trips_a_tool_call_and_observation() -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "reasoning_details": [
                                    {
                                        "type": "reasoning.encrypted",
                                        "data": "opaque-continuation",
                                    }
                                ],
                                "tool_calls": [
                                    {
                                        "id": "write-cache",
                                        "type": "function",
                                        "function": {
                                            "name": "editor",
                                            "arguments": json.dumps(
                                                {
                                                    "operation": "write",
                                                    "path": "src/cache.py",
                                                    "content": "CACHE = {}\n",
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "summary": "Created cache module",
                                    "files": ["src/cache.py"],
                                }
                            ),
                        }
                    }
                ]
            },
        )

    workspace = InMemoryWorkspace()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = OpenRouterModel("example/model", api_key="test-key", client=client)

        result = agent(
            "Create a cache module",
            model=model,
            workspace=workspace,
            tools=[Editor()],
            returns=Change,
        )

    assert result.summary == "Created cache module"
    assert workspace.read_text("src/cache.py") == "CACHE = {}\n"
    assert requests[0]["tools"] == requests[1]["tools"]
    assert requests[0]["tool_choice"] == "required"
    assert "parallel_tool_calls" not in requests[0]
    assert requests[1]["messages"][-2]["tool_calls"][0]["id"] == "write-cache"
    assert requests[1]["messages"][-2]["reasoning_details"] == [
        {
            "type": "reasoning.encrypted",
            "data": "opaque-continuation",
        }
    ]
    assert requests[1]["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "write-cache",
        "name": "editor",
        "content": '{"path":"src/cache.py","written":11}',
    }


def test_openrouter_reports_provider_errors_without_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "Invalid API key"}},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = OpenRouterModel("example/model", api_key="secret-value", client=client)

        with pytest.raises(
            ProviderError,
            match="OpenRouter request failed with HTTP 401: Invalid API key",
        ) as raised:
            agent("Return a string", model=model, returns=str)

    assert "secret-value" not in str(raised.value)


def test_openrouter_returns_truncated_result_arguments_as_feedback() -> None:
    payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        arguments = '{"value": "cut' if len(payloads) == 1 else '{"value": "done"}'
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length" if len(payloads) == 1 else "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"call-{len(payloads)}",
                                    "type": "function",
                                    "function": {"name": "final_result", "arguments": arguments},
                                }
                            ],
                        },
                    }
                ]
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = OpenRouterModel("example/model", api_key="test-key", max_tokens=512, client=client)
        assert agent("Return a string", model=model, returns=str) == "done"

    assert payloads[0]["max_tokens"] == 512
    replayed = payloads[1]["messages"][-2:]
    assert "cut" not in replayed[0]["tool_calls"][0]["function"]["arguments"]
    assert "cut off by the output token limit" in replayed[1]["content"]


def test_openrouter_returns_invalid_tool_arguments_as_feedback() -> None:
    payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        name, arguments = (
            ("editor", "not-json") if len(payloads) == 1 else ("final_result", '{"value": "ok"}')
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"call-{len(payloads)}",
                                    "type": "function",
                                    "function": {"name": name, "arguments": arguments},
                                }
                            ],
                        }
                    }
                ]
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = OpenRouterModel("example/model", api_key="test-key", client=client)
        execution = run_agent(
            "Create a file",
            model=model,
            tools=[Editor()],
            workspace=InMemoryWorkspace(),
            returns=str,
        )

    assert execution.value == "ok"
    assert execution.usage.tool_calls == 0
    assert "editor arguments are not valid JSON" in payloads[1]["messages"][-1]["content"]


def test_openrouter_requires_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY"):
        OpenRouterModel("example/model")


@pytest.mark.parametrize("wrapped", [True, False])
def test_final_result_tool_retry_and_replay(wrapped: bool) -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        parameters = payload["tools"][-1]["function"]["parameters"]
        assert parameters["additionalProperties"] is False
        if wrapped:
            assert parameters["required"] == ["value"]
            assert parameters["properties"]["value"]["type"] == "integer"
        value: Any = "bad" if len(requests) == 1 else 5
        arguments = {"value": value} if wrapped else {"summary": value, "files": []}
        if not wrapped and len(requests) == 1:
            del arguments["files"]
        if not wrapped and len(requests) == 2:
            arguments["summary"] = "done"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "reasoning_details": [
                                {"type": "reasoning.encrypted", "data": "opaque"}
                            ],
                            "tool_calls": [
                                {
                                    "id": "final-1",
                                    "type": "function",
                                    "function": {
                                        "name": "final_result",
                                        "arguments": json.dumps(arguments),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = OpenRouterModel("example/model", api_key="test-key", client=client)
        if wrapped:
            assert agent("Return five", model=model, returns=int) == 5
        else:
            assert agent("Return change", model=model, returns=Change).summary == "done"
    assistant, observation = requests[1]["messages"][-2:]
    assert assistant["tool_calls"][0]["id"] == "final-1"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == (
        {"value": "bad"} if wrapped else {"summary": "bad"}
    )
    assert assistant["reasoning_details"][0]["data"] == "opaque"
    assert observation["tool_call_id"] == "final-1"
    assert "error" in json.loads(observation["content"])


@pytest.mark.parametrize("text", ["", "not JSON", '"wrong"', "null"])
def test_text_fallback_receives_validation_feedback(text: str) -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": text if len(requests) == 1 else "5"}}]}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = OpenRouterModel("example/model", api_key="test-key", client=client)
        assert agent("Return five", model=model, returns=int) == 5
    assert requests[1]["messages"][-1]["name"] == "final_result"
    assert "error" in json.loads(requests[1]["messages"][-1]["content"])


@pytest.mark.parametrize("mixed", [False, True])
def test_multi_call_parse_and_grouped_replay(mixed: bool) -> None:
    requests: list[dict[str, Any]] = []
    calls = [
        {
            "id": "write",
            "type": "function",
            "function": {
                "name": "editor",
                "arguments": json.dumps(
                    {"operation": "write", "path": "one.txt", "content": "saved"}
                ),
            },
        },
        {
            "id": "second",
            "type": "function",
            "function": {
                "name": "final_result" if mixed else "editor",
                "arguments": json.dumps(
                    {"summary": "premature", "files": []}
                    if mixed
                    else {"operation": "read", "path": "one.txt"}
                ),
            },
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            message = {"content": None, "reasoning": "batch", "tool_calls": calls}
        else:
            message = {"content": json.dumps({"summary": "done", "files": ["one.txt"]})}
        return httpx.Response(200, json={"choices": [{"message": message}]})

    workspace = InMemoryWorkspace()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = agent(
            "Write and read",
            model=OpenRouterModel("example/model", api_key="test", client=client),
            returns=Change,
            tools=[Editor()],
            workspace=workspace,
        )
    assert result.summary == "done"
    assistant, first, second = requests[1]["messages"][2:]
    assert assistant["tool_calls"] == calls
    assert assistant["reasoning"] == "batch"
    assert first["tool_call_id"] == "write"
    assert second["tool_call_id"] == "second"
    if mixed:
        assert "final_result alone" in json.loads(second["content"])["error"]
    else:
        assert json.loads(second["content"]) == "saved"
