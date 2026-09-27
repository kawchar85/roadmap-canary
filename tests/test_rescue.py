from __future__ import annotations

import json
import subprocess
from pathlib import Path

from roadmap_canary.evaluation import check_canary
from roadmap_canary.models import CanaryStatus
from roadmap_canary.rescue import PatchRescueAgent
from roadmap_canary.runs import persist_run

from conftest import write_canary_metadata


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _scenario(tmp_path: Path) -> tuple[Path, Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Roadmap Canary Test")

    (repo / "baseline.txt").write_text("baseline\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")

    # The PR occupies the old seam, so the original witness can no longer apply.
    (repo / "feature.txt").write_text("pr-owned\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "change architecture")
    pr_sha = _git(repo, "rev-parse", "HEAD")

    canary = tmp_path / "canary"
    canary.mkdir()
    (canary / "contract.yaml").write_text(
        """version: 1
id: issue-1
feature: demo-feature
must_prove:
  - either the original or an alternate executable path exists
verification:
  commands:
    - python3 -c "from pathlib import Path; f=Path('feature.txt'); a=Path('alternate.txt'); assert (f.exists() and f.read_text() == 'witness\\n') or (a.exists() and a.read_text() == 'alternate\\n')"
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
    return repo, canary, base_sha, pr_sha


def test_successful_rescue_is_path_changed(tmp_path: Path) -> None:
    repo, canary, base_sha, pr_sha = _scenario(tmp_path)
    alternate = tmp_path / "alternate.patch"
    alternate.write_text(
        """diff --git a/alternate.txt b/alternate.txt
new file mode 100644
--- /dev/null
+++ b/alternate.txt
@@ -0,0 +1 @@
+alternate
""",
        encoding="utf-8",
    )

    result = check_canary(
        repo,
        canary,
        base_ref=base_sha,
        pr_ref=pr_sha,
        rescue_agent=PatchRescueAgent(alternate),
    )

    assert result.status == CanaryStatus.PATH_CHANGED
    assert result.rescue is not None
    assert result.rescue.passed
    assert result.rescue.candidate_patch is not None
    assert "alternate.txt" in result.rescue.candidate_patch

    output = persist_run(result, tmp_path / "run")
    persisted = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "PATH_CHANGED"
    assert (output / "replacement-witness.patch").is_file()
    assert "alternate.txt" in (output / "replacement-witness.patch").read_text(
        encoding="utf-8"
    )


def test_failed_rescue_is_roadmap_risk(tmp_path: Path) -> None:
    repo, canary, base_sha, pr_sha = _scenario(tmp_path)
    wrong = tmp_path / "wrong.patch"
    wrong.write_text(
        """diff --git a/wrong.txt b/wrong.txt
new file mode 100644
--- /dev/null
+++ b/wrong.txt
@@ -0,0 +1 @@
+not-a-proof
""",
        encoding="utf-8",
    )

    result = check_canary(
        repo,
        canary,
        base_ref=base_sha,
        pr_ref=pr_sha,
        rescue_agent=PatchRescueAgent(wrong),
    )

    assert result.status == CanaryStatus.ROADMAP_RISK
    assert result.rescue is not None
    assert not result.rescue.passed
    assert "no longer demonstrated" in result.reason.lower()
