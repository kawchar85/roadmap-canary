from __future__ import annotations

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
    It will remain useful in tests after BobRescueAgent is introduced.
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
