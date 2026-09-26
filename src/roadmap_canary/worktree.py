from __future__ import annotations

import subprocess
from pathlib import Path


class GitCommandError(RuntimeError):
    pass


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitCommandError(result.stderr.strip() or result.stdout.strip())
    return result


def create_worktree(repo: str | Path, ref: str, destination: str | Path) -> Path:
    repo_path = Path(repo).resolve()
    destination_path = Path(destination).resolve()

    if destination_path.exists():
        raise FileExistsError(f"Worktree destination already exists: {destination_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    _run_git(repo_path, "worktree", "add", "--detach", str(destination_path), ref)
    return destination_path


def remove_worktree(repo: str | Path, destination: str | Path) -> None:
    repo_path = Path(repo).resolve()
    destination_path = Path(destination).resolve()
    _run_git(repo_path, "worktree", "remove", "--force", str(destination_path))


def stage_all_changes(workspace: str | Path) -> None:
    """Normalize tracked and untracked candidate changes into the worktree index."""

    workspace_path = Path(workspace).resolve()
    _run_git(workspace_path, "add", "-A")


def git_diff(workspace: str | Path) -> str:
    """Return the complete candidate patch relative to the worktree's HEAD."""

    workspace_path = Path(workspace).resolve()
    return _run_git(workspace_path, "diff", "HEAD", "--binary", "--").stdout
