"""Design a small product UI with typed agents and explicit human choices."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pilota import (
    Answer,
    AskHuman,
    Human,
    Limits,
    NoHuman,
    ProgressCallback,
    Question,
    TerminalHuman,
    TerminalProgress,
    agent,
)
from pilota.providers import Model
from pilota.providers.openrouter import OpenRouterModel


@dataclass(frozen=True)
class ProductBrief:
    name: str
    audience: str
    objective: str
    screens: list[str]


@dataclass(frozen=True)
class ProductAnalysis:
    primary_users: list[str]
    critical_tasks: list[str]
    constraints: list[str]
    assumptions: list[str]


@dataclass(frozen=True)
class DesignDirection:
    name: str
    based_on: list[str]
    rationale: str
    density: Literal["compact", "comfortable", "spacious"]
    colors: list[str]
    spacing: list[int]
    radius: int


@dataclass(frozen=True)
class DesignDirections:
    directions: list[DesignDirection]


@dataclass(frozen=True)
class DirectionChoice:
    name: str
    rationale: str


@dataclass(frozen=True)
class DesignTokens:
    background: str
    surface: str
    text: str
    muted_text: str
    accent: str
    on_accent: str
    danger: str
    spacing: list[int]
    radii: list[int]
    font_family: str


@dataclass(frozen=True)
class ComponentRule:
    component: str
    rule: str


@dataclass(frozen=True)
class DesignSystem:
    name: str
    rationale: str
    principles: list[str]
    tokens: DesignTokens
    components: list[ComponentRule]


@dataclass(frozen=True)
class ScreenSpec:
    name: str
    purpose: str
    key_content: list[str]
    states: list[str]


@dataclass(frozen=True)
class ScreenSpecs:
    screens: list[ScreenSpec]


@dataclass(frozen=True)
class PageDraft:
    title: str
    css: str
    body_html: str


@dataclass(frozen=True)
class ReviewIssue:
    severity: Literal["low", "medium", "high"]
    summary: str
    recommendation: str


@dataclass(frozen=True)
class UsabilityReview:
    ok: bool
    issues: list[ReviewIssue]


@dataclass(frozen=True)
class GeneratedScreen:
    name: str
    path: Path
    deterministic_issues: list[str]
    review: UsabilityReview


@dataclass(frozen=True)
class WorkflowResult:
    analysis: ProductAnalysis
    directions: list[DesignDirection]
    chosen_direction: DesignDirection
    design_system: DesignSystem
    screens: list[GeneratedScreen]
    index: Path


DEFAULT_BRIEF = ProductBrief(
    name="Aegis Control",
    audience="Security engineers and service owners protecting public web applications",
    objective="See attacks quickly and change protection safely without reading raw WAF logs",
    screens=["Overview", "Protected domains", "Attack events", "Policy settings"],
)

MODEL_LIMITS = Limits(model_calls=12, tool_calls=8, result_retries=2)
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\b")
SPACING_VALUE = re.compile(
    r"(?:margin|padding|gap)(?:-(?:top|right|bottom|left|inline|block))?\s*:\s*(\d+)px"
)


def analyze_product(
    model: Model,
    human: Human,
    brief: ProductBrief,
    progress: ProgressCallback | None = None,
) -> ProductAnalysis:
    return agent(
        """
        Analyze this product before any visual design work. Ask at most three questions only
        when a missing product fact would materially change the interface. Questions must use
        plain language, offer concrete options, and avoid design terminology. If the person
        delegates a decision, make a reasonable assumption and record it. Return user roles,
        critical tasks, hard constraints, and assumptions. Do not propose visual styling yet.
        """,
        model=model,
        context={"brief": asdict(brief)},
        tools=[AskHuman(human, max_questions=3)],
        limits=MODEL_LIMITS,
        returns=ProductAnalysis,
        progress=progress,
    )


def propose_directions(
    model: Model,
    brief: ProductBrief,
    analysis: ProductAnalysis,
    progress: ProgressCallback | None = None,
) -> list[DesignDirection]:
    result = agent(
        """
        Propose exactly three meaningfully different design directions for the same product.
        Ground each direction in mature public design systems such as Carbon, Primer, Material,
        Polaris, or GOV.UK. Explain why it fits the product instead of inventing a fashionable
        style. Use only six-digit hex colors, a short spacing scale in whole pixels, and one
        radius value. Each direction must support the users, tasks, and constraints in the
        supplied product analysis.
        """,
        model=model,
        context={"brief": asdict(brief), "analysis": asdict(analysis)},
        limits=MODEL_LIMITS,
        returns=DesignDirections,
        progress=progress,
    )
    if len(result.directions) != 3:
        raise ValueError("The model must return exactly three design directions")
    return result.directions


def plan_reference_screen(
    model: Model,
    brief: ProductBrief,
    analysis: ProductAnalysis,
    progress: ProgressCallback | None = None,
) -> ScreenSpec:
    return agent(
        """
        Choose one screen named in the brief that best represents the product's core experience.
        Specify its purpose, essential content, and relevant loading, empty, error, and permission
        states. The same specification will be rendered in three visual directions, so include
        enough representative content and interaction states for a fair comparison. Do not add
        product facts that are absent from the brief or analysis.
        """,
        model=model,
        context={"brief": asdict(brief), "analysis": asdict(analysis)},
        limits=MODEL_LIMITS,
        returns=ScreenSpec,
        progress=progress,
    )


def render_reference_page(
    model: Model,
    brief: ProductBrief,
    analysis: ProductAnalysis,
    screen: ScreenSpec,
    direction: DesignDirection,
    progress: ProgressCallback | None = None,
) -> PageDraft:
    return agent(
        """
        Render the supplied reference-screen specification in this design direction. Return CSS
        and body HTML, not a complete document. Follow the specification exactly so the three
        alternatives compare visual systems rather than different product content. The screen
        must look finished at 1440px and remain usable at 390px. Use semantic HTML. Do not use
        JavaScript, external assets, gradients, or colors and spacing values outside the supplied
        direction.
        """,
        model=model,
        context={
            "brief": asdict(brief),
            "analysis": asdict(analysis),
            "screen": asdict(screen),
            "direction": asdict(direction),
        },
        limits=MODEL_LIMITS,
        returns=PageDraft,
        progress=progress,
    )


def choose_direction(
    model: Model,
    human: Human,
    brief: ProductBrief,
    analysis: ProductAnalysis,
    directions: list[DesignDirection],
    previews: list[Path],
    progress: ProgressCallback | None = None,
) -> DesignDirection:
    answer = human.ask(
        Question(
            "Which visual direction should define the product?",
            options=tuple(direction.name for direction in directions),
            why="Open the three attached pages and compare the same screen in each style.",
            attachments=tuple(previews),
        )
    )
    selected = _selected_direction(answer, directions)
    if selected is not None:
        return selected

    choice = agent(
        """
        The person delegated the visual choice. Select the direction that best supports the
        product's critical tasks and constraints. Return one supplied direction name exactly.
        """,
        model=model,
        context={
            "brief": asdict(brief),
            "analysis": asdict(analysis),
            "directions": [asdict(direction) for direction in directions],
        },
        returns=DirectionChoice,
        progress=progress,
    )
    return _direction_named(choice.name, directions)


def _selected_direction(
    answer: Answer,
    directions: list[DesignDirection],
) -> DesignDirection | None:
    if answer.delegated:
        return None
    value = answer.choices[0] if answer.choices else answer.text
    if value is None:
        return None
    try:
        return _direction_named(value, directions)
    except ValueError:
        return None


def _direction_named(name: str, directions: list[DesignDirection]) -> DesignDirection:
    normalized = name.strip().casefold()
    for direction in directions:
        if direction.name.casefold() == normalized:
            return direction
    raise ValueError(f"Unknown design direction: {name}")


def build_design_system(
    model: Model,
    brief: ProductBrief,
    analysis: ProductAnalysis,
    chosen: DesignDirection,
    rejected: list[DesignDirection],
    progress: ProgressCallback | None = None,
) -> DesignSystem:
    return agent(
        """
        Turn the selected direction into an explicit design system. Explain why the selected
        direction fits better than the rejected alternatives. Define all requested tokens and
        concise rules for navigation, buttons, cards, tables, forms, alerts, and empty states.
        Use six-digit hex colors. The text/background, text/surface, muted-text/surface, and
        on-accent/accent pairs must satisfy WCAG AA contrast. Keep spacing values in whole pixels.
        """,
        model=model,
        context={
            "brief": asdict(brief),
            "analysis": asdict(analysis),
            "chosen": asdict(chosen),
            "rejected": [asdict(direction) for direction in rejected],
        },
        limits=MODEL_LIMITS,
        returns=DesignSystem,
        progress=progress,
    )


def plan_screens(
    model: Model,
    brief: ProductBrief,
    analysis: ProductAnalysis,
    design_system: DesignSystem,
    progress: ProgressCallback | None = None,
) -> list[ScreenSpec]:
    result = agent(
        """
        Specify every screen named in the brief. For each screen, state its purpose, essential
        content, and relevant loading, empty, error, and permission states. Do not add screens or
        visual tokens. Keep the scope small enough for a coherent interactive-looking prototype.
        """,
        model=model,
        context={
            "brief": asdict(brief),
            "analysis": asdict(analysis),
            "design_system": asdict(design_system),
        },
        limits=MODEL_LIMITS,
        returns=ScreenSpecs,
        progress=progress,
    )
    expected = {name.casefold() for name in brief.screens}
    actual = {screen.name.casefold() for screen in result.screens}
    if actual != expected:
        raise ValueError("The model must specify exactly the screens from the brief")
    return result.screens


def generate_screen(
    model: Model,
    brief: ProductBrief,
    analysis: ProductAnalysis,
    design_system: DesignSystem,
    spec: ScreenSpec,
    progress: ProgressCallback | None = None,
) -> PageDraft:
    return agent(
        """
        Generate one polished screen from the supplied specification and design system. Return
        CSS and body HTML, not a complete document. Use semantic HTML and realistic data that is
        consistent with the brief and analysis. Use CSS custom properties for every color. Literal
        color values may appear only in the :root declarations and must come from the supplied
        tokens. Every margin, padding, and gap in pixels must come from the spacing scale. Do not
        use JavaScript, external assets, gradients, inline styles, or unexplained decorative
        elements.
        """,
        model=model,
        context={
            "brief": asdict(brief),
            "analysis": asdict(analysis),
            "design_system": asdict(design_system),
            "screen": asdict(spec),
        },
        limits=MODEL_LIMITS,
        returns=PageDraft,
        progress=progress,
    )


def review_screen(
    model: Model,
    analysis: ProductAnalysis,
    design_system: DesignSystem,
    spec: ScreenSpec,
    page: PageDraft,
    deterministic_issues: list[str],
    progress: ProgressCallback | None = None,
) -> UsabilityReview:
    return agent(
        """
        Review this screen against the product tasks, its specification, the design-system
        principles, and Nielsen's usability heuristics. Treat the supplied deterministic issues
        as facts. Report only concrete problems visible in the HTML/CSS. Set ok only when there
        are no medium or high issues and no deterministic issues.
        """,
        model=model,
        context={
            "analysis": asdict(analysis),
            "design_system": asdict(design_system),
            "screen": asdict(spec),
            "page": asdict(page),
            "deterministic_issues": deterministic_issues,
        },
        limits=MODEL_LIMITS,
        returns=UsabilityReview,
        progress=progress,
    )


def revise_screen(
    model: Model,
    analysis: ProductAnalysis,
    design_system: DesignSystem,
    spec: ScreenSpec,
    page: PageDraft,
    deterministic_issues: list[str],
    review: UsabilityReview,
    progress: ProgressCallback | None = None,
) -> PageDraft:
    return agent(
        """
        Fix the supplied deterministic and usability issues without changing the screen's scope
        or design system. Return the complete replacement CSS and body HTML. Preserve good parts,
        use only supplied tokens, and do not add JavaScript or external assets.
        """,
        model=model,
        context={
            "analysis": asdict(analysis),
            "design_system": asdict(design_system),
            "screen": asdict(spec),
            "page": asdict(page),
            "deterministic_issues": deterministic_issues,
            "review": asdict(review),
        },
        limits=MODEL_LIMITS,
        returns=PageDraft,
        progress=progress,
    )


def deterministic_issues(page: PageDraft, design_system: DesignSystem) -> list[str]:
    tokens = design_system.tokens
    issues = lint_design_system(tokens)
    allowed_colors = {
        tokens.background.casefold(),
        tokens.surface.casefold(),
        tokens.text.casefold(),
        tokens.muted_text.casefold(),
        tokens.accent.casefold(),
        tokens.on_accent.casefold(),
        tokens.danger.casefold(),
    }
    unexpected_colors = sorted(
        {color.casefold() for color in HEX_COLOR.findall(page.css)} - allowed_colors
    )
    if unexpected_colors:
        issues.append(f"Colors outside the token palette: {', '.join(unexpected_colors)}")

    allowed_spacing = set(tokens.spacing)
    unexpected_spacing = sorted(
        {int(value) for value in SPACING_VALUE.findall(page.css)} - allowed_spacing
    )
    if unexpected_spacing:
        values = ", ".join(f"{value}px" for value in unexpected_spacing)
        issues.append(f"Spacing outside the token scale: {values}")
    if re.search(r"\bstyle\s*=", page.body_html, flags=re.IGNORECASE):
        issues.append("Inline styles bypass the design tokens")
    if re.search(r"<script\b", page.body_html, flags=re.IGNORECASE):
        issues.append("JavaScript is outside this static prototype's scope")
    return issues


def lint_design_system(tokens: DesignTokens) -> list[str]:
    issues: list[str] = []
    colors = {
        "background": tokens.background,
        "surface": tokens.surface,
        "text": tokens.text,
        "muted_text": tokens.muted_text,
        "accent": tokens.accent,
        "on_accent": tokens.on_accent,
        "danger": tokens.danger,
    }
    invalid = [name for name, value in colors.items() if HEX_COLOR.fullmatch(value) is None]
    if invalid:
        issues.append(f"Invalid six-digit color tokens: {', '.join(invalid)}")
        return issues

    pairs = [
        ("text/background", tokens.text, tokens.background),
        ("text/surface", tokens.text, tokens.surface),
        ("muted_text/surface", tokens.muted_text, tokens.surface),
        ("on_accent/accent", tokens.on_accent, tokens.accent),
    ]
    for label, foreground, background in pairs:
        ratio = contrast_ratio(foreground, background)
        if ratio < 4.5:
            issues.append(f"{label} contrast is {ratio:.2f}:1; expected at least 4.5:1")
    if not tokens.spacing or any(value < 0 for value in tokens.spacing):
        issues.append("Spacing scale must contain non-negative pixel values")
    if tokens.spacing != sorted(set(tokens.spacing)):
        issues.append("Spacing scale must be sorted and contain unique values")
    return issues


def contrast_ratio(foreground: str, background: str) -> float:
    lighter = max(_relative_luminance(foreground), _relative_luminance(background))
    darker = min(_relative_luminance(foreground), _relative_luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def _relative_luminance(color: str) -> float:
    if HEX_COLOR.fullmatch(color) is None:
        raise ValueError(f"Invalid six-digit hex color: {color}")
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]

    def linearize(channel: float) -> float:
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linearize(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def write_page(path: Path, page: PageDraft) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "<!doctype html>\n"
        '<html lang="en">\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(page.title)}</title>\n"
        f"<style>{page.css}</style>\n"
        f"<body>{page.body_html}</body>\n"
        "</html>\n",
        encoding="utf-8",
    )


def write_index(path: Path, title: str, pages: list[tuple[str, Path]]) -> None:
    links = "\n".join(
        f'<a href="{html.escape(os.path.relpath(page, path.parent))}">{html.escape(name)}</a>'
        for name, page in pages
    )
    page = PageDraft(
        title=title,
        css="""
        :root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
        body { max-width: 760px; margin: 0 auto; padding: 48px 24px; background: #0b1020;
          color: #eef2ff; }
        h1 { font-size: 28px; }
        main { display: grid; gap: 12px; margin-top: 28px; }
        a { padding: 18px; border: 1px solid #334155; border-radius: 12px;
          color: #dbeafe; text-decoration: none; background: #111827; }
        a:hover { border-color: #60a5fa; }
        """,
        body_html=f"<h1>{html.escape(title)}</h1><main>{links}</main>",
    )
    write_page(path, page)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "screen"


def design_ui(
    model: Model,
    human: Human,
    output: Path,
    brief: ProductBrief = DEFAULT_BRIEF,
    *,
    max_revisions: int = 2,
    progress: ProgressCallback | None = None,
) -> WorkflowResult:
    output.mkdir(parents=True, exist_ok=True)
    analysis = analyze_product(model, human, brief, progress)
    directions = propose_directions(model, brief, analysis, progress)
    reference_screen = plan_reference_screen(model, brief, analysis, progress)

    preview_paths: list[Path] = []
    for position, direction in enumerate(directions, start=1):
        page = render_reference_page(model, brief, analysis, reference_screen, direction, progress)
        path = output / "directions" / f"{position}-{_slug(direction.name)}.html"
        write_page(path, page)
        preview_paths.append(path)
    write_index(
        output / "directions" / "index.html",
        "Choose a design direction",
        [(direction.name, path) for direction, path in zip(directions, preview_paths, strict=True)],
    )

    chosen = choose_direction(model, human, brief, analysis, directions, preview_paths, progress)
    rejected = [direction for direction in directions if direction != chosen]
    design_system = build_design_system(model, brief, analysis, chosen, rejected, progress)
    specs = plan_screens(model, brief, analysis, design_system, progress)

    generated: list[GeneratedScreen] = []
    for spec in specs:
        page = generate_screen(model, brief, analysis, design_system, spec, progress)
        issues: list[str] = []
        review = UsabilityReview(ok=False, issues=[])
        for attempt in range(max_revisions + 1):
            issues = deterministic_issues(page, design_system)
            review = review_screen(model, analysis, design_system, spec, page, issues, progress)
            if not issues and review.ok:
                break
            if attempt < max_revisions:
                page = revise_screen(
                    model,
                    analysis,
                    design_system,
                    spec,
                    page,
                    issues,
                    review,
                    progress,
                )
        path = output / "screens" / f"{_slug(spec.name)}.html"
        write_page(path, page)
        generated.append(
            GeneratedScreen(
                name=spec.name,
                path=path,
                deterministic_issues=issues,
                review=review,
            )
        )

    index = output / "index.html"
    write_index(
        index,
        f"{brief.name} prototype",
        [(screen.name, screen.path) for screen in generated],
    )
    (output / "design-system.json").write_text(
        json.dumps(asdict(design_system), indent=2),
        encoding="utf-8",
    )
    return WorkflowResult(
        analysis=analysis,
        directions=directions,
        chosen_direction=chosen,
        design_system=design_system,
        screens=generated,
        index=index,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ui-design-output"),
        help="Directory for generated HTML and design tokens",
    )
    parser.add_argument(
        "--no-human",
        action="store_true",
        help="Let agents make every product and visual decision",
    )
    parser.add_argument("--max-revisions", type=int, default=2)
    args = parser.parse_args()
    if args.max_revisions < 0:
        parser.error("--max-revisions cannot be negative")

    human: Human = NoHuman() if args.no_human else TerminalHuman()
    with OpenRouterModel(os.environ["OPENROUTER_MODEL"]) as model:
        result = design_ui(
            model,
            human,
            args.output,
            max_revisions=args.max_revisions,
            progress=TerminalProgress(),
        )

    print(f"Chosen direction: {result.chosen_direction.name}")
    print(f"Open: {result.index.resolve()}")
    for screen in result.screens:
        status = (
            "passed" if not screen.deterministic_issues and screen.review.ok else "needs review"
        )
        print(f"- {screen.name}: {status}")


if __name__ == "__main__":
    main()
