from __future__ import annotations

import subprocess
from pathlib import Path

from .models import FutureContract, ReplayResult
from .verifier import (
    changed_protected_files,
    changed_protected_tests,
    evaluate_proof_budget,
    run_verification_commands,
    snapshot_protected_files,
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


def _protected_changes(
    workspace: Path,
    contract: FutureContract,
    protected_snapshot: dict[str, str | None],
) -> tuple[list[str], list[str]]:
    changed_tests = changed_protected_tests(
        workspace,
        {
            key: value
            for key, value in protected_snapshot.items()
            if key in contract.protected_tests
        },
    )
    changed_files = changed_protected_files(workspace, protected_snapshot)
    return sorted(changed_tests), sorted(changed_files)


def verify_candidate_workspace(
    workspace: str | Path,
    contract: FutureContract,
    protected_snapshot: dict[str, str | None],
    *,
    timeout_seconds: int = 300,
) -> ReplayResult:
    """Verify code already materialized in an isolated workspace.

    ``protected_snapshot`` must come from the approved BASE state. Protected
    verifier inputs are checked before commands run so a Change cannot replace
    package scripts or test-runner configuration and then have Roadmap Canary
    execute the weakened verifier.
    """

    workspace_path = Path(workspace).resolve()
    changed_tests, changed_files = _protected_changes(
        workspace_path,
        contract,
        protected_snapshot,
    )

    errors: list[str] = []
    if changed_tests:
        errors.append(
            "Protected tests differ from BASE: " + ", ".join(changed_tests)
        )
    if changed_files:
        errors.append(
            "Protected files differ from BASE: " + ", ".join(changed_files)
        )

    # Do not execute verification commands from an untrusted Change when any
    # protected verifier input differs from BASE. Rescue may restore those files
    # to the approved BASE content; verification can then proceed normally.
    if changed_files:
        return ReplayResult(
            workspace=workspace_path,
            patch_applied=True,
            verification_passed=False,
            commands=[],
            protected_tests_unchanged=not changed_tests,
            changed_protected_tests=changed_tests,
            protected_files_unchanged=False,
            changed_protected_files=changed_files,
            budget=None,
            errors=errors,
        )

    command_results = run_verification_commands(
        workspace_path,
        contract,
        timeout_seconds=timeout_seconds,
    )
    verification_passed = (
        len(command_results) == len(contract.verification.commands)
        and all(result.passed for result in command_results)
    )
    budget = evaluate_proof_budget(workspace_path, contract)

    if not verification_passed:
        errors.append("One or more verification commands failed")
    errors.extend(budget.violations)

    return ReplayResult(
        workspace=workspace_path,
        patch_applied=True,
        verification_passed=verification_passed,
        commands=command_results,
        protected_tests_unchanged=True,
        changed_protected_tests=[],
        protected_files_unchanged=True,
        changed_protected_files=[],
        budget=budget,
        errors=errors,
    )


def replay_witness(
    workspace: str | Path,
    witness_patch: str | Path,
    contract: FutureContract,
    *,
    timeout_seconds: int = 300,
    protected_snapshot: dict[str, str | None] | None = None,
) -> ReplayResult:
    """Apply and verify the stored witness in ``workspace``.

    When ``protected_snapshot`` is supplied it is treated as the approved BASE
    trust anchor. This is required for Change replay; otherwise a Change could
    modify a verifier config before the snapshot and compare against itself.
    """

    workspace_path = Path(workspace).resolve()
    witness_path = Path(witness_patch).resolve()
    trusted_snapshot = (
        protected_snapshot
        if protected_snapshot is not None
        else snapshot_protected_files(workspace_path, contract)
    )

    applied, error = _apply_patch(workspace_path, witness_path)
    if not applied:
        changed_tests, changed_files = _protected_changes(
            workspace_path,
            contract,
            trusted_snapshot,
        )
        errors = [error or "Witness patch could not be applied"]
        if changed_tests:
            errors.append(
                "Protected tests differ from BASE: " + ", ".join(changed_tests)
            )
        if changed_files:
            errors.append(
                "Protected files differ from BASE: " + ", ".join(changed_files)
            )
        return ReplayResult(
            workspace=workspace_path,
            patch_applied=False,
            verification_passed=False,
            commands=[],
            protected_tests_unchanged=not changed_tests,
            changed_protected_tests=changed_tests,
            protected_files_unchanged=not changed_files,
            changed_protected_files=changed_files,
            errors=errors,
        )

    return verify_candidate_workspace(
        workspace_path,
        contract,
        trusted_snapshot,
        timeout_seconds=timeout_seconds,
    )
