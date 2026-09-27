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


# ---------------------------------------------------------------------------
# Tests A & B — no shared symlink; source repo remains unchanged
# ---------------------------------------------------------------------------


def test_create_worktree_does_not_share_node_modules_symlink(
    tmp_path: Path,
) -> None:
    """Test A — worktree must not contain a node_modules symlink to the source repo.

    Removing the shared symlink is the primary isolation fix.  This test
    proves the new invariant: after create_worktree() the temporary workspace
    has no node_modules entry at all (directory *or* symlink).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Roadmap Canary Test")

    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    # Simulate an existing node_modules in the source repository.
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "marker.txt").write_text("installed\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "README.md")
    _git(repo, "commit", "-m", "baseline")

    destination = tmp_path / "worktree"
    created = create_worktree(repo, "main", destination)
    try:
        wt_node_modules = created / "node_modules"

        # No symlink into the source repo.
        assert not wt_node_modules.is_symlink(), (
            "create_worktree must not create a node_modules symlink into the source repo"
        )
        # The worktree has no node_modules at all yet — it is clean.
        assert not wt_node_modules.exists(), (
            "Worktree should start without node_modules; install must be done privately"
        )
    finally:
        remove_worktree(repo, destination)


def test_worktree_writes_do_not_reach_source_node_modules(
    tmp_path: Path,
) -> None:
    """Test B — writes inside the worktree must not reach the source repo's node_modules.

    Simulates what happened before the fix: a verification command running
    npm install inside the worktree would follow the symlink and write into
    the user's active checkout.  With the symlink removed this is impossible.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Roadmap Canary Test")

    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "original.js").write_text("original\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "README.md")
    _git(repo, "commit", "-m", "baseline")

    destination = tmp_path / "worktree"
    created = create_worktree(repo, "main", destination)
    try:
        # Simulate what a verification command might write into the worktree's
        # private node_modules (as if npm ci ran there).
        wt_node_modules = created / "node_modules"
        wt_node_modules.mkdir()
        (wt_node_modules / "canary-pkg").mkdir()
        (wt_node_modules / "canary-pkg" / "index.js").write_text(
            "verification artifact\n", encoding="utf-8"
        )

        # Source repo's node_modules must be completely untouched.
        source_nm = repo / "node_modules"
        assert source_nm.is_dir(), "Source node_modules disappeared unexpectedly"
        assert not source_nm.is_symlink(), "Source node_modules became a symlink"
        assert (source_nm / "original.js").read_text(encoding="utf-8") == "original\n"
        # The verification artifact must NOT appear in the source repo.
        assert not (source_nm / "canary-pkg").exists(), (
            "Worktree write leaked into source repository node_modules"
        )
    finally:
        remove_worktree(repo, destination)


# ---------------------------------------------------------------------------
# Test C — installed node_modules excluded from candidate diff / proof budget
# ---------------------------------------------------------------------------


def test_installed_node_modules_absent_from_candidate_diff(tmp_path: Path) -> None:
    """Test C — node_modules installed in the workspace must not appear in the diff.

    After the worktree receives a private npm ci, the installed directory must
    remain invisible to measure_diff(), git_diff(), and stage_all_changes()
    because it is covered by .gitignore.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Roadmap Canary Test")

    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "README.md")
    _git(repo, "commit", "-m", "baseline")

    destination = tmp_path / "worktree"
    created = create_worktree(repo, "main", destination)
    try:
        # Simulate npm ci installing into the private worktree node_modules.
        (created / "node_modules").mkdir()
        (created / "node_modules" / "vitest").mkdir()
        (created / "node_modules" / "vitest" / "index.js").write_text(
            "runtime\n", encoding="utf-8"
        )

        # Also add a real candidate file so we can confirm the diff is not empty.
        (created / "candidate.ts").write_text(
            "export const proof = true;\n", encoding="utf-8"
        )

        stage_all_changes(created)
        diff = git_diff(created)

        # candidate.ts must appear; node_modules must not.
        assert "candidate.ts" in diff, "Candidate file must appear in the diff"
        assert "node_modules" not in diff, (
            "Installed node_modules must not appear in the candidate diff"
        )

        stats = measure_diff(created)
        assert "candidate.ts" in stats.changed_paths
        assert all("node_modules" not in p for p in stats.changed_paths), (
            "measure_diff must not count dependency files as candidate changes"
        )
        assert stats.files_changed == 1
    finally:
        remove_worktree(repo, destination)


# ---------------------------------------------------------------------------
# Test D — fresh isolated verification (no pre-existing node_modules)
# ---------------------------------------------------------------------------


def test_fresh_worktree_has_no_node_modules_on_creation(tmp_path: Path) -> None:
    """Test D — a fresh worktree starts completely clean with no node_modules.

    This is the prerequisite for isolated verification: when the verifier runs
    npm ci as the first verification command the workspace is pristine. After
    that install the diff/budget accounting must still see only real candidate
    changes.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Roadmap Canary Test")

    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "README.md")
    _git(repo, "commit", "-m", "baseline")

    destination = tmp_path / "worktree"
    created = create_worktree(repo, "main", destination)
    try:
        # Verify: no node_modules on fresh creation.
        wt_nm = created / "node_modules"
        assert not wt_nm.exists() and not wt_nm.is_symlink(), (
            "Freshly created worktree must not have node_modules"
        )

        # Simulate npm ci installing dependencies (private installation).
        wt_nm.mkdir()
        (wt_nm / "some-package").mkdir()
        (wt_nm / "some-package" / "index.js").write_text("pkg\n", encoding="utf-8")

        # After install, diff and budget must still report zero changes —
        # node_modules is in .gitignore so it is invisible to Git.
        stats = measure_diff(created)
        assert stats.files_changed == 0
        assert stats.added_lines == 0
        assert stats.changed_paths == []
    finally:
        remove_worktree(repo, destination)


# ---------------------------------------------------------------------------
# Existing regression: stage_all_changes ignores installed node_modules
# ---------------------------------------------------------------------------


def test_stage_all_changes_ignores_installed_node_modules(tmp_path: Path) -> None:
    """Regression: npm install inside a Rescue workspace must not pollute the diff."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Roadmap Canary Test")

    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "README.md")
    _git(repo, "commit", "-m", "baseline")

    # Simulate Bob or a verification command running npm install directly in
    # the Rescue workspace before Roadmap Canary normalizes the candidate.
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "runtime.js").write_text("runtime\n", encoding="utf-8")
    (repo / "candidate.ts").write_text("export const candidate = true;\n", encoding="utf-8")

    stage_all_changes(repo)

    diff = git_diff(repo)
    assert "candidate.ts" in diff
    assert "node_modules" not in diff
    stats = measure_diff(repo)
    assert stats.changed_paths == ["candidate.ts"]
    assert stats.files_changed == 1
