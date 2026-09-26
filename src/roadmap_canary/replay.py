from __future__ import annotations

import subprocess
from pathlib import Path

from .models import FutureContract, ReplayResult
from .verifier import run_verification_commands


def _apply_patch(workspace: Path, witness_patch: Path) -> tuple[bool, str | None]:
    check = subprocess.run(
        ["git", "-C", str(workspace), "apply", "--check", str(witness_patch)],
        text=True,
        capture_output=True,
        check=False,
    )
    if check.returncode != 0:
        return False, check.stderr.strip() or check.stdout.strip()

    apply = subprocess.run(
        ["git", "-C", str(workspace), "apply", str(witness_patch)],
        text=True,
        capture_output=True,
        check=False,
    )
    if apply.returncode != 0:
        return False, apply.stderr.strip() or apply.stdout.strip()

    return True, None


def replay_witness(
    workspace: str | Path,
    witness_patch: str | Path,
    contract: FutureContract,
    *,
    timeout_seconds: int = 300,
) -> ReplayResult:
    workspace_path = Path(workspace).resolve()
    witness_path = Path(witness_patch).resolve()

    applied, error = _apply_patch(workspace_path, witness_path)
    if not applied:
        return ReplayResult(
            workspace=workspace_path,
            patch_applied=False,
            verification_passed=False,
            errors=[error or "Witness patch could not be applied"],
        )

    command_results = run_verification_commands(
        workspace_path,
        contract,
        timeout_seconds=timeout_seconds,
    )
    verification_passed = bool(command_results) and all(
        result.passed for result in command_results
    )

    return ReplayResult(
        workspace=workspace_path,
        patch_applied=True,
        verification_passed=verification_passed,
        commands=command_results,
    )
