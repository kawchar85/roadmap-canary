from __future__ import annotations

import subprocess
from pathlib import Path

from roadmap_canary.evaluation import check_canary, check_known_path
from roadmap_canary.models import CanaryStatus
from roadmap_canary.rescue import PatchRescueAgent

from conftest import write_canary_metadata


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _setup(tmp_path: Path, *, delete_protected: bool = False) -> tuple[Path, Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Roadmap Canary Test")

    (repo / "trusted.cfg").write_text("trusted\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")

    if delete_protected:
        (repo / "trusted.cfg").unlink()
    else:
        (repo / "trusted.cfg").write_text("tampered\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "change verifier input")
    change_sha = _git(repo, "rev-parse", "HEAD")

    canary = tmp_path / "canary"
    canary.mkdir()
    (canary / "contract.yaml").write_text(
        """version: 1
id: issue-1
feature: demo-feature
must_prove:
  - a future proof can be materialized
protected_files:
  - trusted.cfg
verification:
  commands:
    - python3 -c "from pathlib import Path; assert Path('future.txt').read_text() == 'witness\\n'"
proof_budget:
  max_files_changed: 5
  max_added_lines: 20
  max_new_dependencies: 0
""",
        encoding="utf-8",
    )
    (canary / "witness.patch").write_text(
        """diff --git a/future.txt b/future.txt
new file mode 100644
--- /dev/null
+++ b/future.txt
@@ -0,0 +1 @@
+witness
""",
        encoding="utf-8",
    )
    write_canary_metadata(canary, baseline_commit=base_sha)
    return repo, canary, base_sha, change_sha


def test_change_modifying_protected_file_is_compared_to_base(tmp_path: Path) -> None:
    repo, canary, base_sha, change_sha = _setup(tmp_path)

    result = check_known_path(
        repo,
        canary,
        base_ref=base_sha,
        pr_ref=change_sha,
    )

    assert result.base.passed
    assert not result.pr.passed
    assert not result.pr.protected_files_unchanged
    assert result.pr.commands == []
    assert "trusted.cfg" in result.pr.changed_protected_files
    assert result.rescue_required
    assert result.base_protected_snapshot["trusted.cfg"] is not None


def test_change_deleting_protected_file_is_compared_to_base(tmp_path: Path) -> None:
    repo, canary, base_sha, change_sha = _setup(tmp_path, delete_protected=True)

    result = check_known_path(
        repo,
        canary,
        base_ref=base_sha,
        pr_ref=change_sha,
    )

    assert result.base.passed
    assert not result.pr.passed
    assert "trusted.cfg" in result.pr.changed_protected_files
    assert result.rescue_required


def test_rescue_reuses_base_snapshot_not_tampered_change(tmp_path: Path) -> None:
    repo, canary, base_sha, change_sha = _setup(tmp_path)

    rescue_patch = tmp_path / "rescue.patch"
    rescue_patch.write_text(
        """diff --git a/alternate.txt b/alternate.txt
new file mode 100644
--- /dev/null
+++ b/alternate.txt
@@ -0,0 +1 @@
+candidate
""",
        encoding="utf-8",
    )

    result = check_canary(
        repo,
        canary,
        base_ref=base_sha,
        pr_ref=change_sha,
        rescue_agent=PatchRescueAgent(rescue_patch),
    )

    assert result.status == CanaryStatus.ROADMAP_RISK
    assert result.rescue is not None
    assert result.rescue.verification is not None
    verification = result.rescue.verification
    assert not verification.protected_files_unchanged
    assert "trusted.cfg" in verification.changed_protected_files
    # The tampered Change must be rejected before its verification command runs.
    assert verification.commands == []


def test_base_snapshot_is_not_serialized(tmp_path: Path) -> None:
    repo, canary, base_sha, change_sha = _setup(tmp_path)

    result = check_known_path(
        repo,
        canary,
        base_ref=base_sha,
        pr_ref=change_sha,
    )

    assert result.base_protected_snapshot
    assert "base_protected_snapshot" not in result.model_dump()
