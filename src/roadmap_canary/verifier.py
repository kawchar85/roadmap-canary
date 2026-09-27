from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

from .models import BudgetResult, CommandResult, DiffStats, FutureContract


def run_verification_commands(
    workspace: str | Path,
    contract: FutureContract,
    *,
    timeout_seconds: int = 300,
) -> list[CommandResult]:
    """Run human-approved verification commands in the isolated workspace."""

    workspace_path = Path(workspace).resolve()
    results: list[CommandResult] = []

    for command in contract.verification.commands:
        started = time.monotonic()
        try:
            process = subprocess.run(
                command,
                cwd=workspace_path,
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            result = CommandResult(
                command=command,
                exit_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            result = CommandResult(
                command=command,
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=(exc.stderr or "") + f"\nTimed out after {timeout_seconds}s",
                duration_ms=duration_ms,
            )

        results.append(result)
        if not result.passed:
            break

    return results


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workspace_file(workspace: Path, relative_path: str) -> Path:
    candidate = (workspace / relative_path).resolve()
    if not candidate.is_relative_to(workspace):
        raise ValueError(f"Protected path escapes workspace: {relative_path}")
    return candidate


def snapshot_protected_tests(
    workspace: str | Path,
    contract: FutureContract,
) -> dict[str, str | None]:
    """Record protected-test hashes before speculative code is applied.

    Kept for backward compatibility. Use snapshot_protected_files for the
    general protected-file mechanism that also covers vitest configs, package
    manifests, and other trusted verifier inputs.
    """

    workspace_path = Path(workspace).resolve()
    snapshot: dict[str, str | None] = {}
    for relative_path in contract.protected_tests:
        path = _workspace_file(workspace_path, relative_path)
        snapshot[relative_path] = _sha256(path) if path.is_file() else None
    return snapshot


def changed_protected_tests(
    workspace: str | Path,
    snapshot: dict[str, str | None],
) -> list[str]:
    """Return protected-test paths whose content changed after the snapshot.

    Kept for backward compatibility alongside changed_protected_files.
    """
    workspace_path = Path(workspace).resolve()
    changed: list[str] = []
    for relative_path, before in snapshot.items():
        path = _workspace_file(workspace_path, relative_path)
        after = _sha256(path) if path.is_file() else None
        if before != after:
            changed.append(relative_path)
    return changed


def snapshot_protected_files(
    workspace: str | Path,
    contract: FutureContract,
) -> dict[str, str | None]:
    """Record hashes for all protected files (protected_files + protected_tests).

    protected_files covers the full set of trusted verifier inputs: test files,
    test-runner configs, package manifests, and tsconfig. protected_tests is
    kept for backward compatibility; both lists are merged here so a single
    snapshot call protects everything declared in the contract.
    """

    workspace_path = Path(workspace).resolve()
    snapshot: dict[str, str | None] = {}
    all_paths = list(contract.protected_tests) + list(contract.protected_files)
    for relative_path in all_paths:
        if relative_path in snapshot:
            continue
        path = _workspace_file(workspace_path, relative_path)
        snapshot[relative_path] = _sha256(path) if path.is_file() else None
    return snapshot


def changed_protected_files(
    workspace: str | Path,
    snapshot: dict[str, str | None],
) -> list[str]:
    """Return all protected paths (from snapshot) whose content changed."""

    workspace_path = Path(workspace).resolve()
    changed: list[str] = []
    for relative_path, before in snapshot.items():
        path = _workspace_file(workspace_path, relative_path)
        after = _sha256(path) if path.is_file() else None
        if before != after:
            changed.append(relative_path)
    return changed


def _git(
    workspace: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(workspace), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _npm_dependency_names(data: dict[str, object]) -> set[str]:
    names: set[str] = set()
    for section in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ):
        value = data.get(section, {})
        if isinstance(value, dict):
            names.update(str(name) for name in value)
    return names


def count_new_npm_dependencies(workspace: str | Path) -> int:
    """Count newly declared npm dependencies relative to HEAD.

    The hackathon demo repository is TypeScript/npm based, so npm dependency
    declarations are enforced deterministically for the initial MVP.
    """

    workspace_path = Path(workspace).resolve()
    package_path = workspace_path / "package.json"
    if not package_path.is_file():
        return 0

    current = json.loads(package_path.read_text(encoding="utf-8"))
    baseline_result = _git(workspace_path, "show", "HEAD:package.json")
    if baseline_result.returncode != 0:
        baseline: dict[str, object] = {}
    else:
        baseline = json.loads(baseline_result.stdout)

    return len(_npm_dependency_names(current) - _npm_dependency_names(baseline))


def _is_runtime_support_path(workspace: Path, relative_path: str) -> bool:
    """Return True for synthetic worktree-only paths created by Roadmap Canary."""

    if relative_path != "node_modules":
        return False
    path = workspace / relative_path
    return path.is_symlink()


def measure_diff(workspace: str | Path) -> DiffStats:
    """Measure candidate changes relative to HEAD, excluding runtime support paths."""

    workspace_path = Path(workspace).resolve()

    numstat = _git(workspace_path, "diff", "HEAD", "--numstat", "--")
    if numstat.returncode != 0:
        raise RuntimeError(numstat.stderr.strip() or numstat.stdout.strip())

    added_lines = 0
    removed_lines = 0
    diff_paths: set[str] = set()
    for line in numstat.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added, removed, path = parts
        if _is_runtime_support_path(workspace_path, path):
            continue
        diff_paths.add(path)
        if added.isdigit():
            added_lines += int(added)
        if removed.isdigit():
            removed_lines += int(removed)

    status = _git(workspace_path, "status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode != 0:
        raise RuntimeError(status.stderr.strip() or status.stdout.strip())

    changed_paths: set[str] = set()
    untracked_paths: list[str] = []
    for line in status.stdout.splitlines():
        if len(line) < 4:
            continue
        state = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if _is_runtime_support_path(workspace_path, path):
            continue
        changed_paths.add(path)
        if state == "??":
            untracked_paths.append(path)

    # Untracked files are not included in `git diff HEAD --numstat`.
    for relative_path in untracked_paths:
        if relative_path in diff_paths:
            continue
        path = workspace_path / relative_path
        if path.is_file():
            try:
                added_lines += len(path.read_text(encoding="utf-8").splitlines())
            except UnicodeDecodeError:
                pass

    return DiffStats(
        files_changed=len(changed_paths),
        added_lines=added_lines,
        removed_lines=removed_lines,
        new_dependencies=count_new_npm_dependencies(workspace_path),
        changed_paths=sorted(changed_paths),
    )


def evaluate_proof_budget(
    workspace: str | Path,
    contract: FutureContract,
) -> BudgetResult:
    stats = measure_diff(workspace)
    budget = contract.proof_budget
    violations: list[str] = []

    if stats.files_changed > budget.max_files_changed:
        violations.append(
            f"files_changed={stats.files_changed} exceeds max_files_changed={budget.max_files_changed}"
        )
    if stats.added_lines > budget.max_added_lines:
        violations.append(
            f"added_lines={stats.added_lines} exceeds max_added_lines={budget.max_added_lines}"
        )
    if stats.new_dependencies > budget.max_new_dependencies:
        violations.append(
            "new_dependencies="
            f"{stats.new_dependencies} exceeds max_new_dependencies={budget.max_new_dependencies}"
        )

    return BudgetResult(
        passed=not violations,
        stats=stats,
        violations=violations,
    )
