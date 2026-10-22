# Installation

## Core runtime

Create a virtual environment and install Pilota:

=== "pip"

    ```bash
    python -m venv .venv
    . .venv/bin/activate
    pip install pilota
    ```

=== "uv"

    ```bash
    uv venv
    uv pip install pilota
    ```

The core package includes the execution loop, typed results, deterministic model, workspaces,
resources, and built-in tools.

## OpenRouter provider

Install the provider extra when you want to call OpenRouter:

```bash
pip install "pilota[openrouter]"
```

This adds `httpx`. The core runtime does not require an HTTP client.

## Documentation development

For a source checkout:

```bash
git clone https://github.com/hikitani/pilota.git
cd pilota
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev,docs,openrouter]"
mkdocs serve
```

`mkdocs serve` watches the Markdown files and reloads the site locally.

## Verify the installation

```bash
python -c "import pilota; print(pilota.__version__)"
```

You are ready to [run your first agent](first-agent.md).
