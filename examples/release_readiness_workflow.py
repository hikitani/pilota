"""Build and run a repository-specific release review with ordinary Python."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pilota import DirectoryResource, Limits, agent
from pilota.providers import Model
from pilota.providers.openrouter import OpenRouterModel


@dataclass(frozen=True)
class ReviewArea:
    name: str
    objective: str
    paths: list[str]


@dataclass(frozen=True)
class ReviewPlan:
    areas: list[ReviewArea]


@dataclass(frozen=True)
class Finding:
    severity: Literal["low", "medium", "high"]
    summary: str
    evidence: str
    recommendation: str


@dataclass(frozen=True)
class AreaReview:
    area: str
    findings: list[Finding]


@dataclass(frozen=True)
class RemediationPlan:
    actions: list[str]


@dataclass(frozen=True)
class ReleaseReport:
    ready: bool
    summary: str
    blocking_findings: list[str]
    follow_up: list[str]


@dataclass(frozen=True)
class WorkflowResult:
    plan: ReviewPlan
    reviews: list[AreaReview]
    remediation: RemediationPlan | None
    report: ReleaseReport


def review_release(model: Model, repository: Path) -> WorkflowResult:
    source = DirectoryResource(
        repository,
        allow={"list", "read"},
        deny_globs={
            ".env",
            "**/.env",
            ".git/**",
            "**/*.pem",
            "**/*.key",
        },
    )
    read_limits = Limits(model_calls=12, tool_calls=32, result_retries=2)

    plan = agent(
        """
        Plan a focused release-readiness review of this repository.
        Inspect the repository before choosing 2 to 4 independent review areas.
        Each area must have a concrete objective and a short list of relevant paths.
        """,
        model=model,
        resources={"repository": source},
        limits=read_limits,
        returns=ReviewPlan,
    )

    reviews: list[AreaReview] = []
    for area in plan.areas:
        review = agent(
            """
            Review only the assigned area for release blockers.
            Read the relevant repository files and report concrete findings with evidence.
            Use high severity only for an issue that should block the release.
            Return an empty findings list when the area is ready.
            """,
            model=model,
            context={"area": asdict(area)},
            resources={"repository": source},
            limits=read_limits,
            returns=AreaReview,
        )
        reviews.append(review)

    high_findings = [
        finding for review in reviews for finding in review.findings if finding.severity == "high"
    ]

    remediation: RemediationPlan | None = None
    if high_findings:
        remediation = agent(
            """
            Turn the blocking release findings into a minimal ordered remediation plan.
            Do not add unrelated improvements.
            """,
            model=model,
            context={"blocking_findings": [asdict(finding) for finding in high_findings]},
            returns=RemediationPlan,
        )

    report = agent(
        """
        Produce the final release decision using only the supplied review results.
        The release is ready only when there are no high-severity findings.
        Keep the summary concise and put non-blocking work in follow_up.
        """,
        model=model,
        context={
            "reviews": [asdict(review) for review in reviews],
            "remediation": asdict(remediation) if remediation else None,
        },
        returns=ReleaseReport,
    )

    return WorkflowResult(
        plan=plan,
        reviews=reviews,
        remediation=remediation,
        report=report,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "repository",
        type=Path,
        nargs="?",
        default=Path.cwd(),
        help="Repository to review (default: current directory)",
    )
    args = parser.parse_args()

    with OpenRouterModel(os.environ["OPENROUTER_MODEL"]) as model:
        result = review_release(model, args.repository)

    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
