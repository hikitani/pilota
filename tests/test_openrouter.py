import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from pilota import Editor, InMemoryWorkspace, agent
from pilota.errors import ConfigurationError, ProviderError
from pilota.providers.openrouter import OpenRouterModel


@dataclass(frozen=True)
class Change:
    summary: str
    files: list[Path]


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
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert payload["response_format"]["json_schema"]["schema"]["type"] == "object"
        assert payload["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
        assert "tools" not in payload

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
    assert requests[0]["tool_choice"] == "auto"
    assert requests[0]["parallel_tool_calls"] is False
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


def test_openrouter_rejects_invalid_tool_arguments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
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
                                    "id": "broken",
                                    "type": "function",
                                    "function": {
                                        "name": "editor",
                                        "arguments": "not-json",
                                    },
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

        with pytest.raises(ProviderError, match="tool arguments are not valid JSON"):
            agent(
                "Create a file",
                model=model,
                tools=[Editor()],
                workspace=InMemoryWorkspace(),
                returns=str,
            )


def test_openrouter_requires_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY"):
        OpenRouterModel("example/model")
