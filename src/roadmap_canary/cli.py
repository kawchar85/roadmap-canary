from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from .contracts import contract_hash, load_contract

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


if __name__ == "__main__":
    app()
