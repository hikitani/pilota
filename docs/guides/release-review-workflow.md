# Build a repository review workflow

[`examples/release_readiness_workflow.py`](https://github.com/hikitani/pilota/blob/main/examples/release_readiness_workflow.py)
is a complete multi-agent program built from ordinary Python control flow. It reviews a repository
before a release without introducing a workflow graph or hidden shared state.

## The stages

The program makes four decisions visible in code:

1. An agent inspects the repository and returns a typed `ReviewPlan`.
2. A `for` loop runs one narrowly scoped agent call for each `ReviewArea`.
3. An `if` branch requests a `RemediationPlan` only when a review finds a high-severity blocker.
4. A final agent receives the accumulated results and returns a typed `ReleaseReport`.

```python
plan = agent(..., returns=ReviewPlan)

reviews = []
for area in plan.areas:
    reviews.append(
        agent(
            "Review only the assigned area for release blockers.",
            context={"area": asdict(area)},
            resources={"repository": source},
            returns=AreaReview,
        )
    )

high_findings = [
    finding
    for review in reviews
    for finding in review.findings
    if finding.severity == "high"
]

remediation = None
if high_findings:
    remediation = agent(..., returns=RemediationPlan)

report = agent(
    "Produce the final release decision using only the supplied review results.",
    context={
        "reviews": [asdict(review) for review in reviews],
        "remediation": asdict(remediation) if remediation else None,
    },
    returns=ReleaseReport,
)
```

Each call has its own task, result contract, authority, and budget. Later stages know earlier results
only because the Python program passes them explicitly.

## Repository authority

Review stages receive a read-only `DirectoryResource`. Planning and synthesis stages do not receive
ambient filesystem access, and the workflow denies common secret and key paths:

```python
source = DirectoryResource(
    repository,
    allow={"list", "read"},
    deny_globs={".env", "**/.env", ".git/**", "**/*.pem", "**/*.key"},
)
```

The first live run exhausted a 16-operation tool-call budget while inspecting one review area. The
example uses a per-stage limit of 32 tool calls so a model can inspect a medium-sized repository
while still remaining bounded.

## Run it

```bash
export OPENROUTER_API_KEY=...
export OPENROUTER_MODEL=z-ai/glm-5.3-flash
python examples/release_readiness_workflow.py .
```

The program prints the plan, every area review, the optional remediation plan, and the final report
as JSON.

The deterministic tests in
[`tests/test_release_readiness_workflow.py`](https://github.com/hikitani/pilota/blob/main/tests/test_release_readiness_workflow.py)
cover both branches: a blocker creates a remediation plan, while a clean review skips that call.
