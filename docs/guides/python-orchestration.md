# Compose agents with Python

Pilota does not introduce a graph or workflow language. An agent call is a normal expression, so
Python remains the place for sequencing, branching, loops, retries, and concurrency.

## Sequence typed stages

Each stage should have a narrow task and a result contract:

```python
from dataclasses import dataclass

from pilota import agent


@dataclass
class Plan:
    steps: list[str]


@dataclass
class Review:
    approved: bool
    concerns: list[str]


plan = agent(
    "Plan the requested change",
    model=model,
    context={"request": request},
    returns=Plan,
)

review = agent(
    "Review the plan for correctness and missing risks",
    model=model,
    context={"request": request, "plan": plan},
    returns=Review,
)
```

There is no hidden shared memory. The second call knows the first result only because Python passes
it explicitly.

## Branch on a result

```python
if review.approved:
    publish(plan)
else:
    plan = agent(
        "Repair the plan using the review concerns",
        model=model,
        context={
            "request": request,
            "plan": plan,
            "concerns": review.concerns,
        },
        returns=Plan,
    )
```

This keeps the transition visible, testable, and type checked.

## Use ordinary retries for provider failures

Pilota retries invalid final values through `Limits.result_retries`. Application-level retries for
provider availability remain application policy:

```python
from time import sleep

from pilota.errors import ProviderError


def create_plan(request: str) -> Plan:
    for attempt in range(3):
        try:
            return agent(
                "Plan the requested change",
                model=model,
                context={"request": request},
                returns=Plan,
            )
        except ProviderError:
            if attempt == 2:
                raise
            sleep(2**attempt)

    raise AssertionError("unreachable")
```

The retry loop is intentionally outside Pilota because backoff, idempotency, and provider failover
are application decisions.

## Run independent calls concurrently

The synchronous API composes with standard executors:

```python
from concurrent.futures import ThreadPoolExecutor

requests = ["Add caching", "Add metrics", "Add rate limits"]

with ThreadPoolExecutor(max_workers=3) as pool:
    plans = list(pool.map(create_plan, requests))
```

Each call receives its own execution ID, limits, trace, and workspace snapshot. Do not share a
mutable workspace between concurrent executions unless your application provides synchronization.

## Make memory application data

```python
history = load_project_history(project_id)

decision = agent(
    "Choose the next implementation task",
    model=model,
    context={
        "open_tasks": open_tasks,
        "recent_decisions": history[-10:],
    },
    returns=Decision,
)

save_decision(project_id, decision)
```

Pilota does not silently persist conversation state. Your application chooses what to retain,
summarize, remove, and pass into the next call.

## Choose the right boundary

Prefer multiple calls when stages have different:

- result contracts,
- authority,
- budgets,
- failure policies,
- persistence requirements.

Prefer one call when intermediate tool actions serve one outcome and should share one model
conversation.
