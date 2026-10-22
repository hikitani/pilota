import json
import sys
from pathlib import Path

import pytest

from pilota import (
    Artifact,
    DirectoryWorkspace,
    FinalResult,
    InMemoryWorkspace,
    ScriptedModel,
    Shell,
    ToolCall,
    run_agent,
)
from pilota.errors import ConfigurationError, PermissionDenied, ToolError, ToolTimeoutError
from pilota.tools import ToolContext


def test_shell_preserves_arguments_and_uses_workspace_cwd(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    shell = Shell(
        {
            "inspect": [
                sys.executable,
                "-c",
                (
                    "import json, os, sys; "
                    "print(json.dumps({'cwd': os.path.basename(os.getcwd()), "
                    "'args': sys.argv[1:]}))"
                ),
            ]
        }
    )
    workspace = DirectoryWorkspace(tmp_path, allow={"execute"})

    output = shell.invoke(
        {
            "command": "inspect",
            "args": ["two words", "$(not-expanded)"],
            "cwd": "nested",
        },
        ToolContext(execution_id="test", workspace=workspace),
    )

    assert json.loads(output["stdout"]) == {
        "cwd": "nested",
        "args": ["two words", "$(not-expanded)"],
    }
    assert output["exit_code"] == 0
    assert output["stderr"] == ""


def test_shell_collects_files_created_by_a_command(tmp_path: Path) -> None:
    workspace = DirectoryWorkspace(tmp_path, allow={"execute"})
    shell = Shell(
        {
            "generate": [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('generated.txt').write_text('created\\n')",
            ]
        }
    )
    model = ScriptedModel(
        [
            ToolCall(id="generate", name="shell", arguments={"command": "generate"}),
            FinalResult("created"),
        ]
    )

    execution = run_agent(
        "Generate a file",
        model=model,
        workspace=workspace,
        tools=[shell],
        returns=str,
    )

    assert (tmp_path / "generated.txt").read_text() == "created\n"
    assert execution.artifacts == (Artifact(path=Path("generated.txt"), operation="created"),)
    assert model.requests[1].observations[0].output["exit_code"] == 0


def test_shell_requires_workspace_execute_permission(tmp_path: Path) -> None:
    shell = Shell({"status": [sys.executable, "-c", "print('ok')"]})
    workspace = DirectoryWorkspace(tmp_path, allow={"read"})

    with pytest.raises(PermissionDenied, match="execute"):
        shell.invoke(
            {"command": "status"},
            ToolContext(execution_id="test", workspace=workspace),
        )


def test_shell_rejects_cwd_outside_workspace(tmp_path: Path) -> None:
    shell = Shell({"status": [sys.executable, "-c", "print('ok')"]})
    workspace = DirectoryWorkspace(tmp_path, allow={"execute"})

    with pytest.raises(PermissionDenied, match="escapes"):
        shell.invoke(
            {"command": "status", "cwd": ".."},
            ToolContext(execution_id="test", workspace=workspace),
        )


def test_shell_does_not_inherit_process_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PILOTA_TEST_SECRET", "do-not-inherit")
    shell = Shell(
        {
            "environment": [
                sys.executable,
                "-c",
                "import os; print(os.getenv('PILOTA_TEST_SECRET'))",
            ]
        }
    )
    workspace = DirectoryWorkspace(tmp_path, allow={"execute"})

    output = shell.invoke(
        {"command": "environment"},
        ToolContext(execution_id="test", workspace=workspace),
    )

    assert output["stdout"] == "None\n"


def test_shell_environment_is_explicit(tmp_path: Path) -> None:
    shell = Shell(
        {
            "environment": [
                sys.executable,
                "-c",
                "import os; print(os.environ['VISIBLE_VALUE'])",
            ]
        },
        environment={"VISIBLE_VALUE": "configured"},
    )
    workspace = DirectoryWorkspace(tmp_path, allow={"execute"})

    output = shell.invoke(
        {"command": "environment"},
        ToolContext(execution_id="test", workspace=workspace),
    )

    assert output["stdout"] == "configured\n"


def test_shell_truncates_returned_output(tmp_path: Path) -> None:
    shell = Shell(
        {
            "verbose": [
                sys.executable,
                "-c",
                ("import sys; print('abcdef', end=''); print('uvwxyz', end='', file=sys.stderr)"),
            ]
        },
        max_output_chars=4,
    )
    workspace = DirectoryWorkspace(tmp_path, allow={"execute"})

    output = shell.invoke(
        {"command": "verbose"},
        ToolContext(execution_id="test", workspace=workspace),
    )

    assert output["stdout"] == "abcd"
    assert output["stderr"] == "uvwx"
    assert output["stdout_truncated"] is True
    assert output["stderr_truncated"] is True


def test_shell_returns_nonzero_exit_as_an_observation(tmp_path: Path) -> None:
    shell = Shell(
        {
            "fail": [
                sys.executable,
                "-c",
                "import sys; print('invalid', file=sys.stderr); raise SystemExit(7)",
            ]
        }
    )
    workspace = DirectoryWorkspace(tmp_path, allow={"execute"})

    output = shell.invoke(
        {"command": "fail"},
        ToolContext(execution_id="test", workspace=workspace),
    )

    assert output["exit_code"] == 7
    assert output["stderr"] == "invalid\n"


def test_shell_reports_timeout(tmp_path: Path) -> None:
    shell = Shell(
        {
            "wait": [
                sys.executable,
                "-c",
                "import time; time.sleep(1)",
            ]
        },
        timeout=0.01,
    )
    workspace = DirectoryWorkspace(tmp_path, allow={"execute"})

    with pytest.raises(ToolTimeoutError, match="exceeded"):
        shell.invoke(
            {"command": "wait"},
            ToolContext(execution_id="test", workspace=workspace),
        )


def test_shell_rejects_unknown_command_alias(tmp_path: Path) -> None:
    shell = Shell({"allowed": [sys.executable, "-c", "print('ok')"]})
    workspace = DirectoryWorkspace(tmp_path, allow={"execute"})

    with pytest.raises(ToolError, match="not allowed"):
        shell.invoke(
            {"command": "other"},
            ToolContext(execution_id="test", workspace=workspace),
        )


def test_shell_rejects_in_memory_workspace() -> None:
    shell = Shell({"status": [sys.executable, "-c", "print('ok')"]})

    with pytest.raises(ConfigurationError, match="process-backed"):
        shell.invoke(
            {"command": "status"},
            ToolContext(execution_id="test", workspace=InMemoryWorkspace()),
        )
