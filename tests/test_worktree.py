from __future__ import annotations

import subprocess
from pathlib import Path

from roadmap_canary.verifier import measure_diff
from roadmap_canary.worktree import (
    create_worktree,
    git_diff,
    remove_worktree,
    stage_all_changes,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_create_worktree_shares_ignored_node_modules_without_diff_noise(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Roadmap Canary Test")

    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "marker.txt").write_text("installed\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "README.md")
    _git(repo, "commit", "-m", "baseline")

    destination = tmp_path / "worktree"
    created = create_worktree(repo, "main", destination)
    try:
        shared = created / "node_modules"
        assert shared.is_symlink()
        assert (shared / "marker.txt").read_text(encoding="utf-8") == "installed\n"

        # The symlink is runtime infrastructure only. Normalizing candidate
        # changes must not stage, preserve, or count it as part of a Rescue.
        stage_all_changes(created)
        assert git_diff(created) == ""
        stats = measure_diff(created)
        assert stats.files_changed == 0
        assert stats.added_lines == 0
        assert stats.changed_paths == []
    finally:
        remove_worktree(repo, destination)
