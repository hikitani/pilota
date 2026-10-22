from pathlib import Path

import pytest

from pilota import DirectoryWorkspace
from pilota.errors import PermissionDenied


def test_directory_workspace_confines_paths(tmp_path: Path) -> None:
    workspace = DirectoryWorkspace(
        tmp_path,
        allow={"list", "read", "create", "edit"},
    )

    workspace.write_text("src/app.py", "value = 1\n")

    assert workspace.read_text("src/app.py") == "value = 1\n"
    with pytest.raises(PermissionDenied):
        workspace.read_text("../secret.txt")


def test_directory_workspace_enforces_denied_globs(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=secret")
    workspace = DirectoryWorkspace(
        tmp_path,
        allow={"read"},
        deny_globs={".env"},
    )

    with pytest.raises(PermissionDenied):
        workspace.read_text(".env")
