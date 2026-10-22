import importlib.util
import sys
from pathlib import Path

from pilota import FinalResult, ScriptedModel


def load_workflow():
    path = Path(__file__).parents[1] / "examples" / "release_readiness_workflow.py"
    spec = importlib.util.spec_from_file_location("release_readiness_workflow", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.review_release


def test_release_review_builds_remediation_for_blockers(tmp_path: Path) -> None:
    review_release = load_workflow()
    model = ScriptedModel(
        [
            FinalResult(
                {
                    "areas": [
                        {
                            "name": "packaging",
                            "objective": "Check package metadata",
                            "paths": ["pyproject.toml"],
                        },
                        {
                            "name": "tests",
                            "objective": "Check test coverage",
                            "paths": ["tests"],
                        },
                    ]
                }
            ),
            FinalResult(
                {
                    "area": "packaging",
                    "findings": [
                        {
                            "severity": "high",
                            "summary": "Missing license metadata",
                            "evidence": "pyproject.toml has no license field",
                            "recommendation": "Declare the project license",
                        }
                    ],
                }
            ),
            FinalResult({"area": "tests", "findings": []}),
            FinalResult({"actions": ["Declare the project license"]}),
            FinalResult(
                {
                    "ready": False,
                    "summary": "The package metadata blocks release.",
                    "blocking_findings": ["Missing license metadata"],
                    "follow_up": [],
                }
            ),
        ]
    )

    result = review_release(model, tmp_path)

    assert len(result.reviews) == 2
    assert result.remediation is not None
    assert result.remediation.actions == ["Declare the project license"]
    assert result.report.ready is False
    assert len(model.requests) == 5


def test_release_review_skips_remediation_when_ready(tmp_path: Path) -> None:
    review_release = load_workflow()
    model = ScriptedModel(
        [
            FinalResult(
                {
                    "areas": [
                        {
                            "name": "tests",
                            "objective": "Check test coverage",
                            "paths": ["tests"],
                        }
                    ]
                }
            ),
            FinalResult({"area": "tests", "findings": []}),
            FinalResult(
                {
                    "ready": True,
                    "summary": "No release blockers found.",
                    "blocking_findings": [],
                    "follow_up": ["Consider adding more integration tests."],
                }
            ),
        ]
    )

    result = review_release(model, tmp_path)

    assert result.remediation is None
    assert result.report.ready is True
    assert len(model.requests) == 3
