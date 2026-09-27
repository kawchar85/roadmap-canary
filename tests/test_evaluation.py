from __future__ import annotations

import subprocess
from pathlib import Path

from roadmap_canary.evaluation import check_canary, check_known_path, classify_known_path
from roadmap_canary.models import CanaryStatus, ReplayResult

from conftest import write_canary_metadata


def _result(tmp_path: Path, passed: bool) -> ReplayResult:
    return ReplayResult(
        workspace=tmp_path,
        patch_applied=passed,
        verification_passed=passed,
    )


def test_classification_requires_rescue_when_only_pr_fails(tmp_path: Path) -> None:
    result = classify_known_path(
        canary_id="issue-1",
        feature="future-feature",
        base_ref="base",
        pr_ref="pr",
        base=_result(tmp_path / "base", True),
        pr=_result(tmp_path / "pr", False),
    )

    assert result.status is None
    assert result.rescue_required


def test_classification_marks_stale_when_base_already_fails(tmp_path: Path) -> None:
    result = classify_known_path(
        canary_id="issue-1",
        feature="future-feature",
        base_ref="base",
        pr_ref="pr",
        base=_result(tmp_path / "base", False),
        pr=_result(tmp_path / "pr", False),
    )

    assert result.status == CanaryStatus.STALE
    assert not result.rescue_required


def test_check_canary_reuses_supplied_known_path(monkeypatch, tmp_path: Path) -> None:
    known = classify_known_path(
        canary_id="issue-1",
        feature="future-feature",
        base_ref="base",
        pr_ref="pr",
        base=_result(tmp_path / "base", True),
        pr=_result(tmp_path / "pr", True),
    )

    def unexpected_replay(*args, **kwargs):
        raise AssertionError("known path should not be replayed")

    monkeypatch.setattr("roadmap_canary.evaluation.check_known_path", unexpected_replay)

    result = check_canary(
        tmp_path,
        tmp_path / "unused-canary",
        base_ref="base",
        pr_ref="pr",
        rescue_agent=object(),
        known_path=known,
    )

    assert result.status == CanaryStatus.SAFE
    assert result.known_path is known


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_check_known_path_replays_isolated_base_and_pr(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Roadmap Canary Test")

    (repo / "baseline.txt").write_text("baseline\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")

    (repo / "feature.txt").write_text("pr-owned\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "pr changes future seam")
    pr_sha = _git(repo, "rev-parse", "HEAD")

    canary = tmp_path / "canary"
    canary.mkdir()
    (canary / "contract.yaml").write_text(
        """version: 1
id: issue-1
feature: demo-feature
must_prove:
  - witness can add feature.txt
verification:
  commands:
    - python3 -c "from pathlib import Path; assert Path('feature.txt').read_text() == 'witness\\n'"
proof_budget:
  max_files_changed: 2
  max_added_lines: 5
  max_new_dependencies: 0
""",
        encoding="utf-8",
    )
    (canary / "witness.patch").write_text(
        """diff --git a/feature.txt b/feature.txt
new file mode 100644
--- /dev/null
+++ b/feature.txt
@@ -0,0 +1 @@
+witness
""",
        encoding="utf-8",
    )
    write_canary_metadata(canary, baseline_commit=base_sha)

    result = check_known_path(
        repo,
        canary,
        base_ref=base_sha,
        pr_ref=pr_sha,
    )

    assert result.base.passed
    assert not result.pr.passed
    assert result.rescue_required
    assert result.status is None
