from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from .artifacts import load_canary_artifact, sha256_file
from .contracts import contract_hash, load_contract
from .models import CanaryMetadata
from .replay import replay_witness
from .worktree import create_worktree, remove_worktree


class CaptureError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise CaptureError(process.stderr.strip() or process.stdout.strip())
    return process.stdout


def _resolve_commit(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", f"{ref}^{{commit}}").strip()


def capture_canary(
    repo: str | Path,
    contract_path: str | Path,
    *,
    base_ref: str,
    witness_ref: str,
    output_dir: str | Path,
    created_by: str = "human-approved-witness",
    timeout_seconds: int = 300,
) -> Path:
    """Capture a verified witness branch as a portable Roadmap Canary artifact.

    The witness is the binary Git diff from BASE to the witness ref. Before any
    artifact is written, that patch is replayed onto a clean BASE worktree and
    must pass the same deterministic verifier used during normal Canary checks.
    """

    repo_path = Path(repo).resolve()
    contract_file = Path(contract_path).resolve()
    output = Path(output_dir).resolve()

    contract = load_contract(contract_file)
    baseline_commit = _resolve_commit(repo_path, base_ref)
    witness_commit = _resolve_commit(repo_path, witness_ref)

    patch = _git(
        repo_path,
        "diff",
        "--binary",
        baseline_commit,
        witness_commit,
        "--",
    )
    if not patch.strip():
        raise CaptureError("Witness ref has no changes relative to BASE")

    with TemporaryDirectory(prefix="roadmap-canary-capture-") as temporary:
        temp_root = Path(temporary)
        patch_path = temp_root / "witness.patch"
        patch_path.write_text(patch, encoding="utf-8")

        workspace = temp_root / "base"
        create_worktree(repo_path, baseline_commit, workspace)
        try:
            verification = replay_witness(
                workspace,
                patch_path,
                contract,
                timeout_seconds=timeout_seconds,
            )
        finally:
            remove_worktree(repo_path, workspace)

        if not verification.passed:
            details = "; ".join(verification.errors) or "verification failed"
            raise CaptureError(
                "Witness branch is not a valid executable proof on BASE: " + details
            )

        reserved = [
            output / "contract.yaml",
            output / "witness.patch",
            output / "metadata.json",
            output / "evidence.json",
        ]
        if any(path.exists() for path in reserved):
            raise FileExistsError(
                f"Canary artifact already exists at {output}; choose a new directory"
            )

        output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(contract_file, output / "contract.yaml")
        (output / "witness.patch").write_text(patch, encoding="utf-8")

        metadata = CanaryMetadata(
            canary_id=contract.id,
            baseline_commit=baseline_commit,
            contract_hash=contract_hash(contract),
            witness_hash=sha256_file(output / "witness.patch"),
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=created_by,
            status="valid",
        )
        (output / "metadata.json").write_text(
            metadata.model_dump_json(indent=2),
            encoding="utf-8",
        )

        evidence = {
            "base_ref": base_ref,
            "baseline_commit": baseline_commit,
            "witness_ref": witness_ref,
            "witness_commit": witness_commit,
            "verification": json.loads(verification.model_dump_json()),
        }
        (output / "evidence.json").write_text(
            json.dumps(evidence, indent=2),
            encoding="utf-8",
        )

    # Re-open through the normal loader so hash/integrity mistakes fail here.
    load_canary_artifact(output)
    return output
