from __future__ import annotations

import subprocess
from pathlib import Path

from roadmap_canary.models import FutureContract
from roadmap_canary.replay import replay_witness


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Roadmap Canary Test")
    (repo / "baseline.txt").write_text("baseline\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "acceptance.txt").write_text("original\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    return repo


def _contract(**overrides: object) -> FutureContract:
    data: dict[str, object] = {
        "version": 1,
        "id": "issue-1",
        "feature": "demo-feature",
        "must_prove": ["witness exists"],
        "protected_tests": ["tests/acceptance.txt"],
        "verification": {
            "commands": [
                "python3 -c \"from pathlib import Path; assert Path('feature.txt').read_text() == 'witness\\n'\""
            ]
        },
        "proof_budget": {
            "max_files_changed": 2,
            "max_added_lines": 5,
            "max_new_dependencies": 0,
        },
    }
    data.update(overrides)
    return FutureContract.model_validate(data)


def test_replay_accepts_verified_witness(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    patch = tmp_path / "witness.patch"
    patch.write_text(
        """diff --git a/feature.txt b/feature.txt
new file mode 100644
--- /dev/null
+++ b/feature.txt
@@ -0,0 +1 @@
+witness
""",
        encoding="utf-8",
    )

    result = replay_witness(repo, patch, _contract())

    assert result.passed
    assert result.patch_applied
    assert result.verification_passed
    assert result.protected_tests_unchanged
    assert result.budget is not None
    assert result.budget.passed
    assert result.budget.stats.files_changed == 1
    assert result.budget.stats.added_lines == 1


def test_replay_rejects_protected_test_modification(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    patch = tmp_path / "witness.patch"
    patch.write_text(
        """diff --git a/tests/acceptance.txt b/tests/acceptance.txt
--- a/tests/acceptance.txt
+++ b/tests/acceptance.txt
@@ -1 +1 @@
-original
+changed
""",
        encoding="utf-8",
    )
    contract = _contract(
        verification={"commands": ["python3 -c \"print('ok')\""]}
    )

    result = replay_witness(repo, patch, contract)

    assert not result.passed
    assert not result.protected_tests_unchanged
    assert result.changed_protected_tests == ["tests/acceptance.txt"]


def test_replay_rejects_budget_overrun(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    patch = tmp_path / "witness.patch"
    patch.write_text(
        """diff --git a/feature.txt b/feature.txt
new file mode 100644
--- /dev/null
+++ b/feature.txt
@@ -0,0 +1 @@
+witness
""",
        encoding="utf-8",
    )
    contract = _contract(
        proof_budget={
            "max_files_changed": 0,
            "max_added_lines": 0,
            "max_new_dependencies": 0,
        }
    )

    result = replay_witness(repo, patch, contract)

    assert not result.passed
    assert result.budget is not None
    assert not result.budget.passed
    assert result.budget.violations
