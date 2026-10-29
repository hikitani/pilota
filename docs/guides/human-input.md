# Ask a human

An agent may need a detail that is missing from its task. Ask a simple question rather than making
the workflow user understand specialist terms or provide a large specification. Offer a few clear
options when that makes the decision easier.

## Ask between workflow steps

Python can ask directly between agent calls:

```python
from pilota import Question, TerminalHuman, agent

human = TerminalHuman()
audience = human.ask(
    Question(
        "Who will use the dashboard most often?",
        options=("staff, daily", "customers, occasionally"),
        why="helps choose interface density",
    )
)

plan = agent(
    "Plan the dashboard",
    model=model,
    context={"audience": audience},
    returns=DashboardPlan,
)
```

`Answer.choices` contains the selected option text, `Answer.text` contains free text, and
`Answer.delegated` means the human wants the agent to decide.

## Let an agent ask

Provide `AskHuman` as a tool when the missing information may only become clear during the task.
Its question budget limits how often the agent can interrupt:

```python
from pilota import AskHuman, TerminalHuman, agent

result = agent(
    "Design a dashboard for the team",
    model=model,
    tools=[AskHuman(TerminalHuman(), max_questions=3)],
    returns=Dashboard,
)
```

The model is instructed to ask only when information is genuinely missing, use plain language,
prefer options, and state its assumption if the human delegates.

## Use a non-interactive human

`NoHuman` always delegates, which is useful for CI and other non-interactive runs:

```python
from pilota import AskHuman, NoHuman, agent

result = agent(
    "Design a dashboard",
    model=model,
    tools=[AskHuman(NoHuman())],
    returns=Dashboard,
)
```

## Terminal interaction

```text
? Who will use the dashboard most often?
  (helps choose interface density)
  1) staff, daily
  2) customers, occasionally
  0) don't know, decide yourself
>
```

`TerminalHuman` accepts option numbers, free-text alternatives, or `0` to delegate. Without options,
an empty answer delegates.

`ask()` is synchronous and blocking. A wall-time limit or cancellation does not interrupt a question
already waiting for input; the execution boundary checks for them after the answer. Other channels,
such as Slack or Telegram, can be implemented as other `Human` implementations.
