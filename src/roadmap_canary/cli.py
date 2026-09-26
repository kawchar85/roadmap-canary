from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from .contracts import contract_hash, load_contract
from .evaluation import check_known_path
from .models import CanaryStatus

app = typer.Typer(
    no_args_is_help=True,
    help="Executable viability checks for accepted future capabilities.",
)


@app.command()
def validate(contract: Path) -> None:
    """Validate and summarize a Future Contract."""

    try:
        parsed = load_contract(contract)
    except (OSError, ValueError, ValidationError) as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("VALID")
    typer.echo(f"id: {parsed.id}")
    typer.echo(f"feature: {parsed.feature}")
    typer.echo(f"contract_sha256: {contract_hash(parsed)}")


@app.command("check-known-path")
def check_known_path_command(
    repo: Path = typer.Option(..., "--repo", help="Target Git repository."),
    canary: Path = typer.Option(..., "--canary", help="Canary artifact directory."),
    base: str = typer.Option(..., "--base", help="BASE Git ref or commit."),
    pr: str = typer.Option(..., "--pr", help="PR/head Git ref or commit."),
    json_output: bool = typer.Option(False, "--json", help="Emit structured JSON."),
) -> None:
    """Replay the stored witness on BASE and PR without running Rescue."""

    try:
        result = check_known_path(repo, canary, base_ref=base, pr_ref=pr)
    except Exception as exc:  # CLI boundary: render infrastructure/configuration errors.
        typer.echo(f"ENGINE ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        typer.echo("ROADMAP CANARY")
        typer.echo("")
        typer.echo(f"Capability: {result.canary_id} - {result.feature}")
        typer.echo(f"BASE: {'PASS' if result.base.passed else 'FAIL'}")
        typer.echo(f"PR:   {'PASS' if result.pr.passed else 'FAIL'}")
        typer.echo("")
        if result.rescue_required:
            typer.echo("RESULT: RESCUE REQUIRED")
        else:
            typer.echo(f"RESULT: {result.status.value if result.status else 'UNKNOWN'}")
        typer.echo(result.reason)

    if result.rescue_required:
        raise typer.Exit(code=2)
    if result.status == CanaryStatus.STALE:
        raise typer.Exit(code=3)


if __name__ == "__main__":
    app()
