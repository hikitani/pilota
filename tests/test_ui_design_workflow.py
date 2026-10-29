import importlib.util
import sys
from pathlib import Path

from pilota import Answer, FinalResult, ScriptedModel


def load_workflow():
    path = Path(__file__).parents[1] / "examples" / "ui_design_workflow.py"
    spec = importlib.util.spec_from_file_location("ui_design_workflow", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tokens(workflow):
    return workflow.DesignTokens(
        background="#0b1020",
        surface="#111827",
        text="#f8fafc",
        muted_text="#94a3b8",
        accent="#2563eb",
        on_accent="#ffffff",
        danger="#dc2626",
        spacing=[0, 4, 8, 12, 16, 24, 32],
        radii=[0, 6, 12],
        font_family="Inter, system-ui, sans-serif",
    )


def test_contrast_ratio_matches_wcag_reference_values() -> None:
    workflow = load_workflow()

    assert workflow.contrast_ratio("#000000", "#ffffff") == 21
    assert workflow.contrast_ratio("#777777", "#ffffff") == 4.478089453577214


def test_lint_design_system_reports_contrast_and_scale_issues() -> None:
    workflow = load_workflow()
    invalid = workflow.DesignTokens(
        background="#ffffff",
        surface="#ffffff",
        text="#aaaaaa",
        muted_text="#bbbbbb",
        accent="#eeeeee",
        on_accent="#ffffff",
        danger="#ff0000",
        spacing=[8, 4, 8],
        radii=[4],
        font_family="sans-serif",
    )

    issues = workflow.lint_design_system(invalid)

    assert any("text/background contrast" in issue for issue in issues)
    assert any("muted_text/surface contrast" in issue for issue in issues)
    assert any("on_accent/accent contrast" in issue for issue in issues)
    assert "Spacing scale must be sorted and contain unique values" in issues


def test_deterministic_issues_find_token_escapes() -> None:
    workflow = load_workflow()
    design_system = workflow.DesignSystem(
        name="Operational",
        rationale="Fast incident response",
        principles=["Status before decoration"],
        tokens=tokens(workflow),
        components=[],
    )
    page = workflow.PageDraft(
        title="Overview",
        css=".card { color: #123456; padding: 13px; }",
        body_html='<main style="display:block"><script>bad()</script></main>',
    )

    issues = workflow.deterministic_issues(page, design_system)

    assert "Colors outside the token palette: #123456" in issues
    assert "Spacing outside the token scale: 13px" in issues
    assert "Inline styles bypass the design tokens" in issues
    assert "JavaScript is outside this static prototype's scope" in issues


def test_selected_direction_handles_choice_and_delegation() -> None:
    workflow = load_workflow()
    directions = [
        workflow.DesignDirection("Calm", ["Carbon"], "Clear", "compact", [], [], 4),
        workflow.DesignDirection("Bold", ["Primer"], "Visible", "comfortable", [], [], 8),
    ]

    selected = workflow._selected_direction(Answer(choices=("Bold",)), directions)

    assert selected == directions[1]
    assert workflow._selected_direction(Answer(delegated=True), directions) is None


def test_index_links_to_pages_relative_to_index(tmp_path: Path) -> None:
    workflow = load_workflow()
    screen = tmp_path / "screens" / "overview.html"
    screen.parent.mkdir()
    screen.touch()

    index = tmp_path / "index.html"
    workflow.write_index(index, "Prototype", [("Overview", screen)])

    assert 'href="screens/overview.html"' in index.read_text()


def test_reference_page_uses_generated_spec_instead_of_default_product() -> None:
    workflow = load_workflow()
    brief = workflow.ProductBrief(
        name="Parcel Desk",
        audience="Warehouse coordinators",
        objective="Resolve delayed orders",
        screens=["Orders", "Carriers"],
    )
    analysis = workflow.ProductAnalysis(
        primary_users=["Warehouse coordinators"],
        critical_tasks=["Find delayed orders"],
        constraints=["Works on shared terminals"],
        assumptions=[],
    )
    direction = workflow.DesignDirection(
        name="Clear",
        based_on=["GOV.UK"],
        rationale="Prioritizes legibility",
        density="comfortable",
        colors=["#ffffff", "#111111"],
        spacing=[0, 8, 16],
        radius=4,
    )
    model = ScriptedModel(
        [
            FinalResult(
                {
                    "name": "Orders",
                    "purpose": "Resolve delayed orders",
                    "key_content": ["Order status", "Carrier", "Expected arrival"],
                    "states": ["loading", "empty", "error"],
                }
            ),
            FinalResult(
                {
                    "title": "Orders",
                    "css": ":root { color: #111111; background: #ffffff; }",
                    "body_html": "<main><h1>Orders</h1></main>",
                }
            ),
        ]
    )

    screen = workflow.plan_reference_screen(model, brief, analysis)
    workflow.render_reference_page(model, brief, analysis, screen, direction)

    render_request = model.requests[1]
    assert render_request.context["screen"]["name"] == "Orders"
    assert render_request.context["brief"]["name"] == "Parcel Desk"
    task = render_request.task.casefold()
    for product_term in ("waf", "ddos", "attack", "traffic", "protected domains"):
        assert product_term not in task
