# Define typed results

The `returns` argument is the contract between nondeterministic model output and deterministic
application code.

Pilota uses Pydantic's `TypeAdapter` to:

1. derive a JSON Schema for the provider,
2. validate the submitted final value,
3. construct the requested Python value.

## Use dataclasses for simple records

```python
from dataclasses import dataclass


@dataclass
class Finding:
    file: str
    line: int
    message: str


@dataclass
class Review:
    summary: str
    findings: list[Finding]


review = agent(
    "Review the supplied change",
    model=model,
    context={"diff": diff},
    returns=Review,
)
```

Nested records become nested JSON Schema and nested Python values.

## Use Pydantic for richer constraints

```python
from typing import Literal

from pydantic import BaseModel, Field


class Risk(BaseModel):
    severity: Literal["low", "medium", "high"]
    description: str = Field(min_length=1, max_length=500)


class Assessment(BaseModel):
    score: int = Field(ge=0, le=100)
    risks: list[Risk] = Field(max_length=20)
```

Provider schema support varies, but Pilota always validates the final value locally.

## Return collections and scalars

Object models are not required:

```python
labels = agent(
    "Choose applicable labels",
    model=model,
    context={"issue": issue},
    returns=list[str],
)

should_release = agent(
    "Decide whether this build is releasable",
    model=model,
    context={"checks": checks},
    returns=bool,
)
```

OpenRouter wraps non-object schemas in the provider payload and unwraps the value before local
validation.

## Handle invalid results

When validation fails, Pilota sends the validation error back as an observation and allows the
model to submit a corrected result:

```python
from pilota import Limits

assessment = agent(
    "Assess deployment risk",
    model=model,
    returns=Assessment,
    limits=Limits(result_retries=2),
)
```

`result_retries=2` means the initial invalid result can be followed by two corrected attempts.
Every attempt also consumes a model call.

After the retry budget is exhausted, Pilota raises `ResultContractError`.

```python
from pilota.errors import ResultContractError

try:
    assessment = agent(...)
except ResultContractError as error:
    print(error.execution_id)
    print(error.trace)
```

## Model semantic invariants explicitly

Type validation can enforce shape, ranges, enums, and custom Pydantic validators. It cannot prove
that the model's claims are true.

Use Python for invariants that depend on application state:

```python
selection = agent(
    "Select files to update",
    model=model,
    context={"files": allowed_files},
    returns=list[str],
)

unknown = set(selection) - set(allowed_files)
if unknown:
    raise ValueError(f"Model selected unknown files: {sorted(unknown)}")
```

The result contract narrows the boundary. It does not replace domain validation.
