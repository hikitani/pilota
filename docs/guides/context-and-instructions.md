# Supply context and instructions

Pilota keeps task, context, and instructions separate because they have different roles.

| Input | Purpose | Example |
| --- | --- | --- |
| `task` | The outcome for this execution | `"Review the proposed migration"` |
| `context` | Structured application data | diff, ticket, environment facts |
| `instructions` | Reusable behavioral guidance | style, policy, output expectations |

## Pass application data as context

```python
review = agent(
    "Review the proposed migration",
    model=model,
    context={
        "database": "PostgreSQL 16",
        "migration": migration_sql,
        "traffic_profile": traffic_profile,
    },
    returns=MigrationReview,
)
```

Context is a mapping. Providers serialize it for the model, so use JSON-compatible values or values
supported by the provider's serializer.

Avoid flattening data into a long prompt string when the structure matters.

## Pass behavior as instructions

```python
review = agent(
    "Review the proposed migration",
    model=model,
    context={"migration": migration_sql},
    instructions=[
        "Prioritize lock duration and rollback safety.",
        "Report only risks that can change the deployment decision.",
    ],
    returns=MigrationReview,
)
```

Plain strings are literal instruction text. A string that looks like a path is not read from disk.

## Load instruction files explicitly

```python
from pilota import InstructionFile

review = agent(
    "Review the proposed migration",
    model=model,
    instructions=[
        InstructionFile("instructions/database-review.md"),
    ],
    returns=MigrationReview,
)
```

The file is read once, before the first provider call. Missing files, unsupported encodings, and
read failures raise `ConfigurationError`.

Use an explicit encoding when needed:

```python
InstructionFile("instructions/review.md", encoding="utf-8")
```

## Define a custom instruction source

Any object with `render() -> str` can supply an instruction:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TeamPolicy:
    service: str

    def render(self) -> str:
        return policy_store.read_for_service(self.service)


result = agent(
    "Review the change",
    model=model,
    instructions=[TeamPolicy("billing")],
    returns=Review,
)
```

Rendering happens once per execution. Pilota wraps rendering failures as `ConfigurationError`.

## Keep secrets out

Everything in task, context, and rendered instructions can be sent to the provider. Pass credentials
through provider configuration or tool-specific secret handling instead.
