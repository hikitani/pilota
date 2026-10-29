# Build a UI design workflow

[`examples/ui_design_workflow.py`](https://github.com/hikitani/pilota/blob/main/examples/ui_design_workflow.py)
turns a short product brief into a small, consistent HTML prototype. The example uses a WAF and
DDoS protection console, but the workflow is product-agnostic.

## Keep decisions explicit

The program uses typed `agent(...)` calls for product analysis, a reference-screen specification,
design directions, a design system, final screen specifications, generation, and review. Ordinary
Python owns the sequence, loops, files, and revision limit. Product-specific content comes from the
replaceable `ProductBrief` and generated `ScreenSpec`, not from the workflow prompts.

The person is asked for information in two ways:

1. `AskHuman` lets the analysis agent ask up to three plain product questions.
2. `human.ask(Question(...))` presents three rendered versions of the same overview screen and asks
   the person to choose one.

Choosing `don't know, decide yourself` does not stop the workflow. A typed agent call selects the
direction from the product analysis instead.

## Check what models tend to forget

The model produces the design, while normal Python enforces objective rules:

```python
issues = deterministic_issues(page, design_system)
review = review_screen(model, analysis, design_system, spec, page, issues)

if (issues or not review.ok) and attempt < max_revisions:
    page = revise_screen(model, analysis, design_system, spec, page, issues, review)
```

The deterministic pass rejects colors outside the palette, spacing outside the scale, inline styles,
JavaScript, and WCAG AA contrast failures. The agent review checks product tasks, screen requirements,
design principles, and usability heuristics. The revision loop is bounded by ordinary Python.

## Run it

```bash
export OPENROUTER_API_KEY=...
export OPENROUTER_MODEL=z-ai/glm-5.3-flash
python examples/ui_design_workflow.py --output ui-design-output
python -m http.server 8000 --directory ui-design-output
```

Open `http://localhost:8000`. The output contains the final screen index, the three initial visual
directions, and `design-system.json`.

For CI or a fully autonomous run, add `--no-human`. `NoHuman` delegates product questions and the
visual choice to the agents without changing the workflow.
