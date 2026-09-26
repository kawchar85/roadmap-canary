from __future__ import annotations

import json
import subprocess
from pathlib import Path

from roadmap_canary.models import FutureContract, ReplayResult
from roadmap_canary.rescue import BobRescueAgent


def _contract() -> FutureContract:
    return FutureContract.model_validate(
        {
            "version": 1,
            "id": "issue-1",
            "feature": "multiple-payment-providers",
            "must_prove": ["a second provider can use the real checkout path"],
            "protected_tests": ["tests/checkout.integration.test.ts"],
            "verification": {"commands": ["npm test"]},
            "proof_budget": {
                "max_files_changed": 6,
                "max_added_lines": 120,
                "max_new_dependencies": 0,
            },
        }
    )


def _failure(workspace: Path) -> ReplayResult:
    return ReplayResult(
        workspace=workspace,
        patch_applied=False,
        verification_passed=False,
        errors=["old witness no longer applies"],
    )


def _init_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Roadmap Canary Test"],
        check=True,
    )
    (path / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "baseline"], check=True, capture_output=True)


def test_bob_rescue_accepts_json_result_and_detects_workspace_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    _init_repo(workspace)
    agent = BobRescueAgent(bob_binary="true", max_turns=3)

    def fake_invoke(workspace_arg: Path, prompt: str) -> subprocess.CompletedProcess[str]:
        assert "Roadmap Canary Rescue" in prompt
        assert "multiple-payment-providers" in prompt
        assert "tests/checkout.integration.test.ts" in prompt
        (workspace_arg / "bob-proof.txt").write_text(
            "ROADMAP_CANARY_BOB_OK",
            encoding="utf-8",
        )
        payload = {
            "type": "result",
            "timestamp": "2026-09-26T08:04:01.078Z",
            "status": "success",
            "stats": {
                "task_id": "task-123",
                "duration_ms": 5867,
                "session_costs": 0.041754,
                "max_cost": 0,
                "tool_calls": 1,
            },
            "last_message": "Candidate created.",
        }
        return subprocess.CompletedProcess(
            args=["bob", "run"],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(agent, "_invoke_bob", fake_invoke)

    result = agent.rescue(workspace, _contract(), _failure(workspace))

    assert result.candidate_produced
    assert result.task_id == "task-123"
    assert result.duration_ms == 5867
    assert result.cost == 0.041754
    assert result.tool_calls == 1
    assert result.last_message == "Candidate created."


def test_bob_rescue_rejects_success_without_workspace_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    _init_repo(workspace)
    agent = BobRescueAgent(bob_binary="true", max_turns=3)

    def fake_invoke(workspace_arg: Path, prompt: str) -> subprocess.CompletedProcess[str]:
        del workspace_arg, prompt
        return subprocess.CompletedProcess(
            args=["bob", "run"],
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "result",
                    "timestamp": "2026-09-26T08:04:01.078Z",
                    "status": "success",
                    "stats": {
                        "task_id": "task-empty",
                        "duration_ms": 100,
                        "session_costs": 0.01,
                        "tool_calls": 0,
                    },
                    "last_message": "No changes required.",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(agent, "_invoke_bob", fake_invoke)

    result = agent.rescue(workspace, _contract(), _failure(workspace))

    assert not result.candidate_produced
    assert any("no candidate workspace changes" in error.lower() for error in result.errors)


def test_bob_result_parser_handles_single_json_line() -> None:
    payload = {
        "type": "result",
        "status": "success",
        "stats": {"task_id": "abc"},
        "last_message": "done",
    }

    assert BobRescueAgent._parse_result(json.dumps(payload)) == payload
