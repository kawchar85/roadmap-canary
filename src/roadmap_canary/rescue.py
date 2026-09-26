from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from .models import FutureContract, ReplayResult, RescueRun


class RescueAgent(Protocol):
    """A component that proposes candidate code inside an isolated worktree."""

    name: str

    def rescue(
        self,
        workspace: Path,
        contract: FutureContract,
        failure: ReplayResult,
    ) -> RescueRun:
        ...


class PatchRescueAgent:
    """Development/test Rescue adapter that applies a prepared alternate patch.

    This proves the Roadmap Canary orchestration independently from IBM Bob.
    It remains useful for deterministic tests after BobRescueAgent is introduced.
    """

    name = "prepared-patch"

    def __init__(self, patch_path: str | Path) -> None:
        self.patch_path = Path(patch_path).resolve()

    def rescue(
        self,
        workspace: Path,
        contract: FutureContract,
        failure: ReplayResult,
    ) -> RescueRun:
        del contract, failure

        check = subprocess.run(
            [
                "git",
                "-C",
                str(workspace),
                "apply",
                "--check",
                "--index",
                str(self.patch_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if check.returncode != 0:
            return RescueRun(
                agent=self.name,
                candidate_produced=False,
                errors=[check.stderr.strip() or check.stdout.strip()],
            )

        apply = subprocess.run(
            [
                "git",
                "-C",
                str(workspace),
                "apply",
                "--index",
                str(self.patch_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if apply.returncode != 0:
            return RescueRun(
                agent=self.name,
                candidate_produced=False,
                errors=[apply.stderr.strip() or apply.stdout.strip()],
            )

        return RescueRun(
            agent=self.name,
            candidate_produced=True,
        )


class BobRescueAgent:
    """Invoke IBM Bob Shell to propose a replacement viability proof.

    Bob is intentionally only the proposal mechanism. The caller independently
    measures the resulting Git diff and runs deterministic verification.
    """

    name = "ibm-bob"

    def __init__(
        self,
        *,
        bob_binary: str = "bob",
        max_turns: int = 8,
        timeout_seconds: int = 600,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least 1")

        self.bob_binary = bob_binary
        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds

    def _build_prompt(
        self,
        contract: FutureContract,
        failure: ReplayResult,
    ) -> str:
        protected_tests = "\n".join(
            f"- {path}" for path in contract.protected_tests
        ) or "- none configured"

        return f"""You are performing a Roadmap Canary Rescue inside an isolated Git worktree.

A previously verified executable witness for an accepted future capability no longer verifies on the current PR state. Your job is to produce the smallest candidate code change that demonstrates a new viable path satisfying the SAME Future Contract.

IMPORTANT ROLE BOUNDARY
- You propose code only.
- Do not decide or claim SAFE, PATH_CHANGED, ROADMAP_RISK, or any final Roadmap Canary verdict.
- An external deterministic verifier will evaluate your changes after you exit.

FUTURE CONTRACT (authoritative, human-approved)
{contract.model_dump_json(indent=2)}

PREVIOUS WITNESS FAILURE EVIDENCE
{failure.model_dump_json(indent=2)}

REQUIRED WORKING RULES
- Edit files directly in the current workspace.
- Produce the smallest credible executable proof satisfying the contract.
- Use real production paths required by the contract; do not bypass them with isolated fake logic.
- Preserve existing behavior.
- Do not weaken, delete, or rewrite approved acceptance/contract tests merely to make the proof pass.
- Do not replace production components with mocks unless the Future Contract explicitly allows it.
- Do not make unrelated refactors.
- Stay within the Future Contract proof budget.
- Do not commit any changes.
- If the capability can be demonstrated, leave the candidate implementation in the workspace for external verification.
- If you cannot produce a credible candidate within the constraints, do not create unrelated placeholder changes.

PROTECTED TESTS
{protected_tests}

When finished, respond briefly with what you changed. The external verifier, not you, determines whether the Rescue succeeded.
"""

    def _invoke_bob(
        self,
        workspace: Path,
        prompt: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                self.bob_binary,
                "run",
                "--workspace",
                str(workspace),
                "--mode",
                "agent",
                "--format",
                "json",
                "--max-turns",
                str(self.max_turns),
                prompt,
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=self.timeout_seconds,
        )

    @staticmethod
    def _parse_result(stdout: str) -> dict[str, object] | None:
        text = stdout.strip()
        if not text:
            return None

        candidates = [text]
        candidates.extend(reversed([line.strip() for line in text.splitlines() if line.strip()]))
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed.get("type") == "result":
                return parsed
        return None

    @staticmethod
    def _workspace_has_changes(workspace: Path) -> tuple[bool, str | None]:
        status = subprocess.run(
            ["git", "-C", str(workspace), "status", "--porcelain"],
            text=True,
            capture_output=True,
            check=False,
        )
        if status.returncode != 0:
            return False, status.stderr.strip() or status.stdout.strip()
        return bool(status.stdout.strip()), None

    def rescue(
        self,
        workspace: Path,
        contract: FutureContract,
        failure: ReplayResult,
    ) -> RescueRun:
        if shutil.which(self.bob_binary) is None:
            return RescueRun(
                agent=self.name,
                candidate_produced=False,
                errors=[f"IBM Bob Shell executable not found: {self.bob_binary}"],
            )

        prompt = self._build_prompt(contract, failure)
        try:
            process = self._invoke_bob(workspace, prompt)
        except subprocess.TimeoutExpired:
            return RescueRun(
                agent=self.name,
                candidate_produced=False,
                errors=[f"IBM Bob Rescue timed out after {self.timeout_seconds}s"],
            )

        parsed = self._parse_result(process.stdout)
        if parsed is None:
            error = process.stderr.strip() or "Bob did not return a parseable JSON result"
            return RescueRun(
                agent=self.name,
                candidate_produced=False,
                errors=[error],
            )

        stats = parsed.get("stats")
        stats_dict = stats if isinstance(stats, dict) else {}
        task_id = stats_dict.get("task_id")
        duration_ms = stats_dict.get("duration_ms")
        cost = stats_dict.get("session_costs")
        tool_calls = stats_dict.get("tool_calls")
        last_message = parsed.get("last_message")

        if process.returncode != 0 or parsed.get("status") != "success":
            message = process.stderr.strip() or f"Bob run status: {parsed.get('status')}"
            return RescueRun(
                agent=self.name,
                candidate_produced=False,
                task_id=str(task_id) if task_id is not None else None,
                duration_ms=int(duration_ms) if isinstance(duration_ms, (int, float)) else None,
                cost=float(cost) if isinstance(cost, (int, float)) else None,
                tool_calls=int(tool_calls) if isinstance(tool_calls, (int, float)) else None,
                last_message=str(last_message) if last_message is not None else None,
                errors=[message],
            )

        changed, git_error = self._workspace_has_changes(workspace)
        errors = [git_error] if git_error else []
        if not changed and not errors:
            errors.append("Bob completed successfully but left no candidate workspace changes")

        return RescueRun(
            agent=self.name,
            candidate_produced=changed,
            task_id=str(task_id) if task_id is not None else None,
            duration_ms=int(duration_ms) if isinstance(duration_ms, (int, float)) else None,
            cost=float(cost) if isinstance(cost, (int, float)) else None,
            tool_calls=int(tool_calls) if isinstance(tool_calls, (int, float)) else None,
            last_message=str(last_message) if last_message is not None else None,
            errors=errors,
        )
