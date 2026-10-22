# Contributing

## Set up the project

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev,docs,openrouter]"
```

## Run the checks

```bash
pytest
ruff check .
ruff format --check .
mypy
mkdocs build --strict
```

Live OpenRouter tests are opt-in because they use an external service:

```bash
PILOTA_RUN_OPENROUTER_TESTS=1 \
OPENROUTER_API_KEY=... \
OPENROUTER_MODEL=... \
pytest tests/integration/test_openrouter_live.py
```

## Documentation conventions

- Teach one concept at a time and link forward to the next dependency.
- Keep examples executable and use public imports where possible.
- Separate verified runtime behavior from future design.
- Put task-specific recipes in guides and stable signatures in the reference.
- Run `mkdocs build --strict` before opening a pull request.

The long-form [design specification](design.md) records project philosophy, non-goals, and
deferred decisions. It is not a substitute for user documentation.
