from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from .capture import CaptureError, capture_canary
from .contracts import contract_hash, load_contract
from .evaluation import check_canary, check_known_path
from .models import CanaryStatus
from .promote import PromotionError, promote_verified_rescue
from .rescue import BobRescueAgent, PatchRescueAgent
from .runs import persist_run

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


@app.command()
def capture(
    repo: Path = typer.Option(..., "--repo", help="Target Git repository."),
    contract: Path = typer.Option(..., "--contract", help="Approved Future Contract YAML."),
    base: str = typer.Option(..., "--base", help="BASE Git ref or commit."),
    witness: str = typer.Option(..., "--witness", help="Git ref containing the verified witness implementation."),
    output: Path = typer.Option(..., "--output", help="Directory to create for the Canary artifact."),
) -> None:
    """Capture and verify a witness branch as a portable Canary artifact."""

    try:
        artifact_dir = capture_canary(
            repo,
            contract,
            base_ref=base,
            witness_ref=witness,
            output_dir=output,
        )
    except (OSError, ValueError, ValidationError, CaptureError) as exc:
        typer.echo(f"CAPTURE FAILED: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("CANARY CAPTURED")
    typer.echo(f"artifact: {artifact_dir}")
    typer.echo(f"contract: {artifact_dir / 'contract.yaml'}")
    typer.echo(f"witness: {artifact_dir / 'witness.patch'}")
    typer.echo(f"metadata: {artifact_dir / 'metadata.json'}")
    typer.echo(f"evidence: {artifact_dir / 'evidence.json'}")


@app.command()
def promote(
    repo: Path = typer.Option(..., "--repo", help="Target Git repository."),
    canary: Path = typer.Option(..., "--canary", help="Existing Canary artifact directory."),
    run_dir: Path = typer.Option(..., "--run-dir", help="Evidence directory from a successful PATH_CHANGED run."),
) -> None:
    """Explicitly promote a verified Rescue patch as the new stored witness."""

    try:
        promoted = promote_verified_rescue(repo, canary, run_dir)
    except (OSError, ValueError, ValidationError, PromotionError) as exc:
        typer.echo(f"PROMOTION FAILED: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("CANARY WITNESS PROMOTED")
    typer.echo(f"artifact: {promoted}")
    typer.echo("The replacement proof was re-verified before the trusted witness changed.")


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


@app.command()
def check(
    repo: Path = typer.Option(..., "--repo", help="Target Git repository."),
    canary: Path = typer.Option(..., "--canary", help="Canary artifact directory."),
    base: str = typer.Option(..., "--base", help="BASE Git ref or commit."),
    pr: str = typer.Option(..., "--pr", help="PR/head Git ref or commit."),
    rescue_patch: Path | None = typer.Option(
        None,
        "--rescue-patch",
        help=(
            "Use a prepared alternate proof instead of IBM Bob. "
            "Intended for deterministic development/testing."
        ),
    ),
    bob_max_turns: int = typer.Option(
        8,
        "--bob-max-turns",
        min=1,
        help="Maximum turns for one IBM Bob Rescue attempt.",
    ),
    bob_max_cost: float = typer.Option(
        0.50,
        "--bob-max-cost",
        min=0.001,
        help="Maximum Bobcoins for one IBM Bob Rescue attempt.",
    ),
    bob_timeout: int = typer.Option(
        600,
        "--bob-timeout",
        min=1,
        help="Wall-clock timeout in seconds for one IBM Bob Rescue attempt.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Write result.json and any replacement witness patch here.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit structured JSON."),
) -> None:
    """Run witness replay plus one bounded Rescue attempt.

    IBM Bob is the default Rescue backend. Supplying --rescue-patch switches to
    the deterministic prepared-patch adapter used by development tests.
    """

    rescue_agent = (
        PatchRescueAgent(rescue_patch)
        if rescue_patch is not None
        else BobRescueAgent(
            max_turns=bob_max_turns,
            max_cost=bob_max_cost,
            timeout_seconds=bob_timeout,
        )
    )

    try:
        result = check_canary(
            repo,
            canary,
            base_ref=base,
            pr_ref=pr,
            rescue_agent=rescue_agent,
        )
        if output_dir is not None:
            persist_run(result, output_dir)
    except Exception as exc:
        typer.echo(f"ENGINE ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        known = result.known_path
        typer.echo("ROADMAP CANARY")
        typer.echo("")
        typer.echo(f"Capability: {known.canary_id} - {known.feature}")
        typer.echo(f"BASE: {'PASS' if known.base.passed else 'FAIL'}")
        typer.echo(f"PR:   {'PASS' if known.pr.passed else 'FAIL'}")
        if result.rescue is not None:
            typer.echo(
                "RESCUE: "
                + ("PASS" if result.rescue.passed else "NO VERIFIED PROOF")
            )
            typer.echo(f"Agent: {result.rescue.agent}")
            if result.rescue.cost is not None:
                typer.echo(f"Bob cost: {result.rescue.cost:.6f}")
            if result.rescue.task_id is not None:
                typer.echo(f"Bob task: {result.rescue.task_id}")
        typer.echo("")
        label = (
            "PATH CHANGED - SAFE"
            if result.status == CanaryStatus.PATH_CHANGED
            else result.status.value
        )
        typer.echo(f"RESULT: {label}")
        typer.echo(result.reason)
        if output_dir is not None:
            typer.echo(f"Evidence: {output_dir.resolve()}")

    if result.status == CanaryStatus.ROADMAP_RISK:
        raise typer.Exit(code=2)
    if result.status == CanaryStatus.STALE:
        raise typer.Exit(code=3)


@app.command()
def ui(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Interface to bind. Keep 127.0.0.1 for local-only access.",
    ),
    port: int = typer.Option(8765, "--port", min=1, max=65535),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open a browser automatically."),
) -> None:
    """Launch the local Roadmap Canary web interface."""

    import threading
    import webbrowser

    import uvicorn

    url = f"http://{host}:{port}"
    typer.echo(f"ROADMAP CANARY UI: {url}")
    typer.echo("Press Ctrl+C to stop.")
    if not no_open and host in {"127.0.0.1", "localhost"}:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    uvicorn.run("roadmap_canary.ui:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    app()
