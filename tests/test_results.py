import pytest
from pydantic import BaseModel, ConfigDict

from pilota import FinalResult, Limits, ScriptedModel, agent
from pilota.errors import ResultContractError


class Plan(BaseModel):
    model_config = ConfigDict(strict=True)

    steps: list[str]
    effort: int


def test_agent_returns_pydantic_model() -> None:
    model = ScriptedModel(
        [
            FinalResult(
                {
                    "steps": ["Inspect the project", "Implement the change"],
                    "effort": 3,
                }
            )
        ]
    )

    result = agent(
        "Create a plan",
        model=model,
        returns=Plan,
    )

    assert isinstance(result, Plan)
    assert result == Plan(
        steps=["Inspect the project", "Implement the change"],
        effort=3,
    )
    assert model.requests[0].result_schema["properties"]["effort"]["type"] == "integer"


def test_pydantic_model_configuration_is_enforced() -> None:
    model = ScriptedModel(
        [
            FinalResult(
                {
                    "steps": ["Inspect the project"],
                    "effort": "3",
                }
            )
        ]
    )

    with pytest.raises(ResultContractError):
        agent(
            "Create an invalid plan",
            model=model,
            returns=Plan,
            limits=Limits(result_retries=0),
        )
