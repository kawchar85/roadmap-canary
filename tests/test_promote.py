from __future__ import annotations

import subprocess
from pathlib import Path

from roadmap_canary.artifacts import load_canary_artifact
from roadmap_canary.evaluation import check_canary
from roadmap_canary.models import CanaryStatus
from roadmap_canary.promote import promote_verified_rescue
from roadmap_canary.rescue import PatchRescueAgent
from roadmap_canary.runs import persist_run


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_verified_rescue_can_be_explicitly_promoted(tmp_path: Path) -> None:
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
    _git(repo, "commit", "-m", "change architecture")
    pr_sha = _git(repo, "rev-parse", "HEAD")

    canary = tmp_path / "canary"
    canary.mkdir()
    (canary / "contract.yaml").write_text(
        '''version: 1
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
''',
        encoding="utf-8",
    )
    (canary / "witness.patch").write_text(
        '''diff --git a/feature.txt b/feature.txt
new file mode 100644
--- /dev/null
+++ b/feature.txt
@@ -0,0 +1 @@
+witness
''',
        encoding="utf-8",
    )

    alternate = tmp_path / "alternate.patch"
    alternate.write_text(
        '''diff --git a/alternate.txt b/alternate.txt
new file mode 100644
--- /dev/null
+++ b/alternate.txt
@@ -0,0 +1 @@
+alternate
''',
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

    run_dir = tmp_path / "run"
    persist_run(result, run_dir)
    promote_verified_rescue(repo, canary, run_dir)

    artifact = load_canary_artifact(canary)
    assert artifact.metadata is not None
    assert artifact.metadata.baseline_commit == pr_sha
    assert artifact.metadata.created_by == "verified-rescue:prepared-patch"
    assert "alternate.txt" in artifact.witness_path.read_text(encoding="utf-8")
