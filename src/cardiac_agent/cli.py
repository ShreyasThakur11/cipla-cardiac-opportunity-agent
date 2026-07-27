"""Command-line interface.

The fastest path from a cloned repository to an answer, and the surface used by
the evaluation suite. Every command is safe to re-run.

    cardiac-agent build          build the warehouse from the workbook
    cardiac-agent ask "..."      answer one question
    cardiac-agent rank           print a scorecard
    cardiac-agent whitespace     underpenetrated spaces
    cardiac-agent sensitivity    rank stability under randomised weights
    cardiac-agent export         write the full analysis to disk
    cardiac-agent doctor         check the installation
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from .config import PROJECT_ROOT, get_framework, get_settings
from .logging_config import configure_logging

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="AI agent for prioritising opportunity spaces in the India Cardiac market.",
)
console = Console()


def _console_table(title: str, rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> Table:
    table = Table(title=title, header_style="bold", show_lines=False)
    for _, heading in columns:
        table.add_column(heading, overflow="fold")
    for row in rows:
        table.add_row(*[_format_cell(row.get(key)) for key, _ in columns])
    return table


def _format_cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


@app.command()
def build(
    workbook: Path | None = typer.Option(None, help="Path to the Cardiac workbook."),
    force: bool = typer.Option(False, "--force", help="Rebuild even if a warehouse exists."),
) -> None:
    """Ingest the workbook and build the DuckDB warehouse."""
    from .ingestion import build_warehouse
    from .pipeline import reset_context_cache

    configure_logging()
    settings = get_settings()

    if settings.warehouse_path.exists() and not force:
        console.print(
            f"[yellow]A warehouse already exists at {settings.warehouse_path}.[/] "
            "Rebuilding it (pass --force to silence this notice)."
        )

    metadata = build_warehouse(workbook=workbook)
    reset_context_cache()

    console.print("[bold green]Warehouse built.[/]")
    for key in (
        "sku_rows",
        "space_rows",
        "market_value_latest_cr",
        "focal_value_latest_cr",
        "focal_share_pct",
        "as_of",
    ):
        console.print(f"  {key.replace('_', ' ')}: [bold]{metadata[key]}[/]")
    console.print(f"  source digest: {metadata['source_sha256'][:16]}...")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Your question about the Cardiac market."),
    show_evidence: bool = typer.Option(False, "--evidence", help="Print the raw evidence pack."),
    show_trace: bool = typer.Option(False, "--trace", help="Print the execution trace."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of prose."),
) -> None:
    """Ask the agent a question."""
    from .agent import build_agent

    configure_logging()
    agent = build_agent()
    result = agent.ask(question)

    if json_output:
        console.print_json(json.dumps(result.to_dict(include_evidence=show_evidence), default=str))
        return

    console.print(Markdown(result.answer))

    if result.citations:
        console.print("\n[bold]Sources[/]")
        for citation in result.citations:
            console.print(f"  [{citation['id']}] {citation['title']} - {citation['publisher']}")
            if citation["url"] and not citation["url"].startswith("internal://"):
                console.print(f"      {citation['url']}")

    if show_trace:
        console.print("\n[bold]Trace[/]")
        console.print_json(json.dumps(result.state.to_trace(), default=str))

    if show_evidence:
        console.print("\n[bold]Evidence[/]")
        console.print_json(json.dumps(result.evidence, default=str))


@app.command()
def rank(
    level: str = typer.Option("molecule_combination", help="Space level to rank."),
    by: str = typer.Option("cipla_priority_score", help="Score to rank on."),
    top: int = typer.Option(10, help="How many rows."),
) -> None:
    """Print the scorecard for one space level."""
    from .pipeline import get_context

    configure_logging()
    context = get_context()
    frame = context.scored[context.scored["level"] == level]
    if frame.empty:
        console.print(f"[red]No spaces at level '{level}'.[/]")
        raise typer.Exit(code=1)

    rows = frame.sort_values(by, ascending=False).head(top).to_dict(orient="records")
    for row in rows:
        for key in ("value_yoy", "real_growth", "focal_share_t2"):
            row[key] = row[key] * 100.0

    console.print(
        _console_table(
            f"{level.replace('_', ' ').title()} ranked by {by.replace('_', ' ')}",
            rows,
            [
                ("space_label", "Space"),
                ("value_t2", f"Size ({context.currency_unit})"),
                ("value_yoy", "Growth %"),
                ("real_growth", "Real %"),
                ("hhi", "HHI"),
                ("focal_share_t2", "Cipla %"),
                ("market_opportunity_index", "Opportunity"),
                ("right_to_win_score", "Right to win"),
                ("cipla_priority_score", "Priority"),
                ("strategic_verdict", "Verdict"),
            ],
        )
    )


@app.command()
def whitespace(limit: int = typer.Option(10, help="How many rows.")) -> None:
    """Attractive spaces where Cipla is underweight but has a route in."""
    from .analytics.whitespace import find_whitespace
    from .pipeline import get_context

    configure_logging()
    context = get_context()
    result = find_whitespace(
        context.scored,
        focal_overall_share=context.totals["focal_share"],
        levels=["sub_segment", "molecule_combination", "anchor_molecule"],
        limit=limit,
    )
    if result.empty:
        console.print("[yellow]No space cleared all three whitespace tests.[/]")
        return

    rows = result.to_dict(orient="records")
    for row in rows:
        row["focal_share_t2"] = row["focal_share_t2"] * 100.0

    console.print(
        _console_table(
            "Underpenetrated spaces with a credible route in",
            rows,
            [
                ("space_label", "Space"),
                ("value_t2", "Size"),
                ("focal_share_t2", "Cipla %"),
                ("value_gap_cr", "Gap to fair share"),
                ("market_opportunity_index", "Opportunity"),
                ("route_to_win", "Route in"),
            ],
        )
    )


@app.command()
def sensitivity(
    level: str = typer.Option("molecule_combination", help="Space level to test."),
    top_k: int = typer.Option(5, help="Size of the top set to track."),
    iterations: int | None = typer.Option(None, help="Randomised weightings to run."),
) -> None:
    """Test how stable the ranking is under randomised framework weights."""
    from .analytics.sensitivity import run_sensitivity
    from .pipeline import get_context

    configure_logging()
    context = get_context()
    result = run_sensitivity(
        context.enriched,
        level=level,
        framework=context.framework,
        iterations=iterations,
        top_k=top_k,
    )
    rows = result.stability.head(12).to_dict(orient="records")
    console.print(
        _console_table(
            f"Rank stability over {result.iterations} randomised weightings",
            rows,
            [
                ("space_label", "Space"),
                ("baseline_rank", "Base rank"),
                ("top_k_frequency", f"In top {top_k}"),
                ("mean_rank", "Mean rank"),
                ("worst_rank", "Worst"),
            ],
        )
    )
    console.print(
        "\n[dim]Above 0.80 the recommendation is robust to how the framework is weighted. "
        "Below 0.60 it is a judgement call and should be presented as one.[/]"
    )


@app.command()
def export(
    destination: Path = typer.Option(PROJECT_ROOT / "exports", help="Output directory."),
) -> None:
    """Write the full analysis to CSV and JSON for the deck and the appendix."""
    from .pipeline import get_context

    configure_logging()
    context = get_context()
    destination.mkdir(parents=True, exist_ok=True)

    context.scored.to_csv(destination / "scorecard.csv", index=False)
    context.score.excluded.to_csv(destination / "excluded_spaces.csv", index=False)
    context.company_facts.to_csv(destination / "company_facts.csv", index=False)

    payload = {
        "metadata": context.metadata,
        "totals": context.totals,
        "weights": context.score.weights,
        "notes": context.notes,
        "citations": context.citations(),
    }
    (destination / "analysis_metadata.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )

    console.print(f"[bold green]Exported to {destination}[/]")
    for name in ("scorecard.csv", "excluded_spaces.csv", "company_facts.csv", "analysis_metadata.json"):
        console.print(f"  {name}")


@app.command()
def doctor() -> None:
    """Check that the installation is complete and consistent."""
    configure_logging()
    settings = get_settings()
    ok = True

    console.print("[bold]Configuration[/]")
    console.print(f"  project root: {PROJECT_ROOT}")
    console.print(f"  config file:  {settings.config_file} {'OK' if settings.config_file.exists() else 'MISSING'}")
    if not settings.config_file.exists():
        ok = False

    console.print("\n[bold]Data[/]")
    try:
        workbook = settings.resolve_data_file()
        console.print(f"  workbook: {workbook} OK")
    except FileNotFoundError as exc:
        console.print(f"  [red]workbook: {exc}[/]")
        ok = False

    warehouse = settings.warehouse_path
    console.print(f"  warehouse: {warehouse} {'OK' if warehouse.exists() else 'NOT BUILT - run `cardiac-agent build`'}")
    if not warehouse.exists():
        ok = False

    signals = sorted(settings.signals_dir.glob("*.md")) if settings.signals_dir.exists() else []
    console.print(f"  external signals: {len(signals)} document(s)")
    if not signals:
        console.print("  [yellow]No signals found; trend multipliers will be neutral.[/]")

    console.print("\n[bold]Model[/]")
    console.print(f"  provider: {settings.llm_provider}")
    console.print(f"  model:    {settings.llm_model}")
    console.print(f"  effort:   {settings.llm_effort}")
    if settings.llm_available:
        console.print("  credentials: found")
    else:
        console.print(
            "  [yellow]credentials: not found - the agent will answer deterministically, "
            "which is fully supported.[/]"
        )

    console.print("\n[bold]Framework[/]")
    try:
        framework = get_framework()
        moi = framework.require("scoring.moi_weights")
        console.print(f"  MOI weights: {moi} (sum {sum(moi.values()):.3f})")
    except (KeyError, FileNotFoundError, ValueError) as exc:
        console.print(f"  [red]{exc}[/]")
        ok = False

    if warehouse.exists():
        try:
            from .pipeline import get_context

            context = get_context()
            console.print(
                f"\n[bold]Analysis[/]\n  spaces scored: {len(context.scored)}\n"
                f"  market value:  {context.totals['market_value_t2']:,.0f} {context.currency_unit}\n"
                f"  Cipla share:   {context.totals['focal_share'] * 100:.2f}%"
            )
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [red]context failed to build: {exc}[/]")
            ok = False

    console.print(
        "\n[bold green]All checks passed.[/]" if ok else "\n[bold red]Some checks failed.[/]"
    )
    raise typer.Exit(code=0 if ok else 1)


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Bind address."),
    port: int | None = typer.Option(None, help="Port."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes."),
) -> None:
    """Run the FastAPI service."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "cardiac_agent.api.main:app",
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=reload,
    )


if __name__ == "__main__":  # pragma: no cover
    app()
