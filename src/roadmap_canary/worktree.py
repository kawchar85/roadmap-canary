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


def _share_ignored_node_modules(repo: Path, destination: Path) -> None:
    """Reuse installed Node dependencies without polluting the candidate diff.

    Git worktrees do not copy untracked directories such as ``node_modules``.
    Roadmap Canary often verifies JavaScript/TypeScript repositories in several
    temporary worktrees, so requiring a fresh network install for every replay
    would make verification slow and brittle.

    If the target repository already has ``node_modules`` installed and that
    directory is ignored by Git, expose it in the temporary worktree through a
    symlink. Internal Git operations explicitly exclude this synthetic symlink
    from candidate-change detection and staging.
    """

    source = repo / "node_modules"
    target = destination / "node_modules"
    if not source.is_dir() or target.exists() or target.is_symlink():
        return

    ignored = subprocess.run(
        ["git", "-C", str(destination), "check-ignore", "-q", "node_modules/"],
        text=True,
        capture_output=True,
        check=False,
    )
    if ignored.returncode != 0:
        return

    target.symlink_to(source, target_is_directory=True)


def create_worktree(repo: str | Path, ref: str, destination: str | Path) -> Path:
    repo_path = Path(repo).resolve()
    destination_path = Path(destination).resolve()

    if destination_path.exists():
        raise FileExistsError(f"Worktree destination already exists: {destination_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    _run_git(repo_path, "worktree", "add", "--detach", str(destination_path), ref)
    _share_ignored_node_modules(repo_path, destination_path)
    return destination_path


def remove_worktree(repo: str | Path, destination: str | Path) -> None:
    repo_path = Path(repo).resolve()
    destination_path = Path(destination).resolve()
    _run_git(repo_path, "worktree", "remove", "--force", str(destination_path))


def stage_all_changes(workspace: str | Path) -> None:
    """Normalize candidate changes into the index, excluding runtime dependencies."""

    workspace_path = Path(workspace).resolve()
    _run_git(
        workspace_path,
        "add",
        "-A",
        "--",
        ".",
        ":(exclude)node_modules",
    )


def git_diff(workspace: str | Path) -> str:
    """Return the complete candidate patch relative to the worktree's HEAD."""

    workspace_path = Path(workspace).resolve()
    return _run_git(workspace_path, "diff", "HEAD", "--binary", "--").stdout
