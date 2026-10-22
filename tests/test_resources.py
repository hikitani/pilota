from dataclasses import dataclass

from pilota import DirectoryResource, FinalResult, ScriptedModel, ToolCall, run_agent


@dataclass(frozen=True)
class Selection:
    names: list[str]


def test_directory_resource_is_exposed_as_scoped_tool(tmp_path) -> None:
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "python.md").write_text("Use Python.")

    model = ScriptedModel(
        [
            ToolCall(
                id="list-skills",
                name="resource_skill_catalog",
                arguments={"operation": "list", "arguments": {"path": "."}},
            ),
            FinalResult({"names": ["python.md"]}),
        ]
    )

    execution = run_agent(
        "Select useful skills",
        model=model,
        resources={"skill_catalog": DirectoryResource(skills)},
        returns=Selection,
    )

    assert execution.value == Selection(names=["python.md"])
    assert model.requests[1].observations[0].output == ["python.md"]
