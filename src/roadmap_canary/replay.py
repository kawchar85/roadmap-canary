from __future__ import annotations

import subprocess
from pathlib import Path

from .models import FutureContract, ReplayResult
from .verifier import (
    changed_protected_tests,
    evaluate_proof_budget,
    run_verification_commands,
    snapshot_protected_tests,
)


def _apply_patch(workspace: Path, witness_patch: Path) -> tuple[bool, str | None]:
    check = subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "apply",
            "--check",
            "--index",
            str(witness_patch),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if check.returncode != 0:
        return False, check.stderr.strip() or check.stdout.strip()

    apply = subprocess.run(
        ["git", "-C", str(workspace), "apply", "--index", str(witness_patch)],
        text=True,
        capture_output=True,
        check=False,
    )
    if apply.returncode != 0:
        return False, apply.stderr.strip() or apply.stdout.strip()

    return True, None


def verify_candidate_workspace(
    workspace: str | Path,
    contract: FutureContract,
    protected_snapshot: dict[str, str | None],
    *,
    timeout_seconds: int = 300,
) -> ReplayResult:
    """Verify code already materialized in an isolated workspace.

    This is used after a Rescue agent proposes candidate code. The external
    verifier, not the agent, decides whether the candidate counts as evidence.
    """

    workspace_path = Path(workspace).resolve()
    command_results = run_verification_commands(
        workspace_path,
        contract,
        timeout_seconds=timeout_seconds,
    )
    verification_passed = (
        len(command_results) == len(contract.verification.commands)
        and all(result.passed for result in command_results)
    )

    changed_tests = changed_protected_tests(workspace_path, protected_snapshot)
    budget = evaluate_proof_budget(workspace_path, contract)

    errors: list[str] = []
    if not verification_passed:
        errors.append("One or more verification commands failed")
    if changed_tests:
        errors.append(
            "Protected tests were modified: " + ", ".join(sorted(changed_tests))
        )
    errors.extend(budget.violations)

    return ReplayResult(
        workspace=workspace_path,
        patch_applied=True,
        verification_passed=verification_passed,
        commands=command_results,
        protected_tests_unchanged=not changed_tests,
        changed_protected_tests=sorted(changed_tests),
        budget=budget,
        errors=errors,
    )


def replay_witness(
    workspace: str | Path,
    witness_patch: str | Path,
    contract: FutureContract,
    *,
    timeout_seconds: int = 300,
) -> ReplayResult:
    workspace_path = Path(workspace).resolve()
    witness_path = Path(witness_patch).resolve()
    protected_snapshot = snapshot_protected_tests(workspace_path, contract)

    applied, error = _apply_patch(workspace_path, witness_path)
    if not applied:
        return ReplayResult(
            workspace=workspace_path,
            patch_applied=False,
            verification_passed=False,
            errors=[error or "Witness patch could not be applied"],
        )

    return verify_candidate_workspace(
        workspace_path,
        contract,
        protected_snapshot,
        timeout_seconds=timeout_seconds,
    )
