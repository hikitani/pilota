# Grant tools and resources

By default, an agent can only reason over its task, context, and instructions. It cannot read files,
run commands, call your services, or mutate state.

Authority is added through three distinct inputs:

| Input | Role |
| --- | --- |
| `tools` | Callable actions the model may request |
| `resources` | Named external data or services exposed as operations |
| `workspace` | The file state tools may access and modify |

## Add a tool

A tool publishes a model-facing schema and handles validated-looking, but still untrusted,
arguments:

```python
from collections.abc import Mapping
from typing import Any

from pilota.models import ToolSpec
from pilota.tools import ToolContext


class TicketLookup:
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ticket_lookup",
            description="Read one engineering ticket by its identifier.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
        )

    def invoke(
        self,
        arguments: Mapping[str, Any],
        context: ToolContext,
    ) -> Any:
        ticket_id = arguments.get("id")
        if not isinstance(ticket_id, str):
            raise ValueError("id must be a string")
        return ticket_store.read(ticket_id)
```

Pass the instance explicitly:

```python
result = agent(
    "Summarize the requested ticket",
    model=model,
    tools=[TicketLookup()],
    returns=Summary,
)
```

Tool names must be unique. `final_result` is reserved by Pilota.

## Add a resource

Resources group operations under a caller-chosen name. Pilota exposes each resource to the model as
one generated tool named `resource_<name>`.

```python
from pilota import DirectoryResource

result = agent(
    "Explain the public package",
    model=model,
    resources={
        "source": DirectoryResource(
            "src",
            allow={"list", "read"},
            deny_globs={"**/.env", "**/*.pem"},
        )
    },
    returns=Explanation,
)
```

The model sees `resource_source` with `list` and `read` operations. It does not receive ambient
filesystem access.

## Separate read authority from mutation

Use resources for external information and a workspace for mutable task state:

```python
from pilota import DirectoryResource, DirectoryWorkspace, Editor

reference = DirectoryResource("reference", allow={"list", "read"})
workspace = DirectoryWorkspace(
    "working-copy",
    allow={"list", "read", "create", "edit"},
    deny_globs={"**/.env", "**/.git/**"},
)

execution = run_agent(
    "Update the implementation using the reference material",
    model=model,
    resources={"reference": reference},
    workspace=workspace,
    tools=[Editor()],
    returns=ChangeSummary,
)
```

This makes the data flow visible:

```text
reference resource ── read ──► agent
                                  │
                                  ▼
                            editor tool
                                  │
                                  ▼
                         mutable workspace
```

## Treat tool arguments as untrusted

JSON Schema improves model behavior; it is not an authorization boundary. Every tool and resource
implementation must validate arguments and enforce permissions at invocation time.

Read [the authority model](../concepts/authority-model.md) for the security implications.
