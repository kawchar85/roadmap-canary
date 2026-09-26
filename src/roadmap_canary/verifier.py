from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .models import CommandResult, FutureContract


def run_verification_commands(
    workspace: str | Path,
    contract: FutureContract,
    *,
    timeout_seconds: int = 300,
) -> list[CommandResult]:
    """Run human-approved verification commands in the isolated workspace.

    Future Contracts are trusted repository configuration. Commands are therefore
    executed through the platform shell so normal project commands such as
    `npm test` and `npm run typecheck` work unchanged.
    """

    workspace_path = Path(workspace).resolve()
    results: list[CommandResult] = []

    for command in contract.verification.commands:
        started = time.monotonic()
        try:
            process = subprocess.run(
                command,
                cwd=workspace_path,
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            result = CommandResult(
                command=command,
                exit_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            result = CommandResult(
                command=command,
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=(exc.stderr or "") + f"\nTimed out after {timeout_seconds}s",
                duration_ms=duration_ms,
            )

        results.append(result)
        if not result.passed:
            break

    return results
