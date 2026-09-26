from __future__ import annotations

from pathlib import Path

import pytest

from roadmap_canary.ui import (
    _display_ref,
    _repository_slug,
    _resolve_inside_repo,
    _result_summary,
)


def test_resolve_inside_repo_accepts_relative_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / ".roadmap-canary" / "issue-1"
    target.mkdir(parents=True)

    resolved = _resolve_inside_repo(repo, ".roadmap-canary/issue-1")

    assert resolved == target.resolve()


def test_resolve_inside_repo_rejects_escape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(ValueError, match="inside the selected repository"):
        _resolve_inside_repo(repo, "../outside")


def test_repository_slug_accepts_owner_repo_and_dot_git() -> None:
    assert _repository_slug("kawchar85/roadmap-canary-demo") == "kawchar85/roadmap-canary-demo"
    assert _repository_slug("kawchar85/roadmap-canary-demo.git") == "kawchar85/roadmap-canary-demo"


def test_repository_slug_rejects_local_paths_and_urls() -> None:
    assert _repository_slug("/tmp/roadmap-canary-demo") is None
    assert _repository_slug("../roadmap-canary-demo") is None
    assert _repository_slug("git@github.com:kawchar85/roadmap-canary-demo.git") is None


def test_display_ref_hides_origin_prefix() -> None:
    assert _display_ref("origin/demo/path-changed-safe") == "demo/path-changed-safe"
    assert _display_ref("main") == "main"
    assert _display_ref(None) is None


def test_result_summary_exposes_deterministic_budget_failure() -> None:
    data = {
        "status": "ROADMAP_RISK",
        "reason": "proof budget exceeded",
        "known_path": {
            "canary_id": "issue-1",
            "feature": "multiple-payment-providers",
            "base_ref": "origin/main",
            "pr_ref": "origin/demo/roadmap-risk",
            "base": {"patch_applied": True, "verification_passed": True},
            "pr": {"patch_applied": False, "verification_passed": False},
        },
        "rescue": {
            "attempted": True,
            "candidate_produced": True,
            "candidate_patch": "diff --git a/a.ts b/a.ts\n",
            "agent": "ibm-bob",
            "cost": 0.9,
            "task_id": "task-1",
            "verification": {
                "verification_passed": True,
                "protected_tests_unchanged": True,
                "commands": [
                    {"command": "npm test", "exit_code": 0},
                    {"command": "npm run typecheck", "exit_code": 0},
                ],
                "budget": {
                    "passed": False,
                    "stats": {
                        "files_changed": 5,
                        "added_lines": 51,
                        "removed_lines": 22,
                        "new_dependencies": 0,
                    },
                    "violations": ["files_changed=5 exceeds max_files_changed=3"],
                },
            },
        },
    }

    summary = _result_summary(data)

    assert summary["status_label"] == "ROADMAP_RISK"
    assert summary["base_passed"] is True
    assert summary["pr_passed"] is False
    assert summary["base_display_ref"] == "main"
    assert summary["pr_display_ref"] == "demo/roadmap-risk"
    assert summary["rescue"]["candidate_produced"] is True
    assert summary["rescue"]["candidate_patch"].startswith("diff --git")
    assert summary["rescue"]["passed"] is False
    assert summary["verification"]["passed"] is True
    assert summary["verification"]["budget_passed"] is False
    assert summary["verification"]["budget"]["files_changed"] == 5
    assert summary["verification"]["budget_violations"] == [
        "files_changed=5 exceeds max_files_changed=3"
    ]
