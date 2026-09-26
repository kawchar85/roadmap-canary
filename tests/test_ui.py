from __future__ import annotations

from pathlib import Path

import pytest

from roadmap_canary.ui import _resolve_inside_repo, _result_summary


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


def test_result_summary_exposes_deterministic_budget_failure() -> None:
    data = {
        "status": "ROADMAP_RISK",
        "reason": "proof budget exceeded",
        "known_path": {
            "canary_id": "issue-1",
            "feature": "multiple-payment-providers",
            "base_ref": "main",
            "pr_ref": "origin/demo/roadmap-risk",
            "base": {"patch_applied": True, "verification_passed": True},
            "pr": {"patch_applied": False, "verification_passed": False},
        },
        "rescue": {
            "attempted": True,
            "candidate_produced": True,
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
    assert summary["rescue"]["candidate_produced"] is True
    assert summary["rescue"]["passed"] is False
    assert summary["verification"]["passed"] is True
    assert summary["verification"]["budget_passed"] is False
    assert summary["verification"]["budget"]["files_changed"] == 5
    assert summary["verification"]["budget_violations"] == [
        "files_changed=5 exceeds max_files_changed=3"
    ]
