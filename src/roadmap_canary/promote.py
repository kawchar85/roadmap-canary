from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from .artifacts import load_canary_artifact, sha256_file
from .contracts import contract_hash
from .models import CanaryCheck, CanaryMetadata, CanaryStatus
from .replay import replay_witness
from .worktree import create_worktree, remove_worktree


class PromotionError(RuntimeError):
    pass


def _resolve_commit(repo: Path, ref: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", f"{ref}^{{commit}}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise PromotionError(process.stderr.strip() or process.stdout.strip())
    return process.stdout.strip()


def promote_verified_rescue(
    repo: str | Path,
    canary: str | Path,
    run_dir: str | Path,
    *,
    timeout_seconds: int = 300,
) -> Path:
    """Promote a verified PATH_CHANGED Rescue into the stored witness.

    Promotion is intentionally explicit. A successful Bob Rescue does not mutate
    the trusted Canary artifact until a human invokes this operation.
    """

    repo_path = Path(repo).resolve()
    canary_path = Path(canary).resolve()
    run_path = Path(run_dir).resolve()

    artifact = load_canary_artifact(canary_path)
    result_path = run_path / "result.json"
    replacement_path = run_path / "replacement-witness.patch"

    if not result_path.is_file():
        raise PromotionError(f"Missing run result: {result_path}")
    if not replacement_path.is_file():
        raise PromotionError(f"Missing verified replacement witness: {replacement_path}")

    result = CanaryCheck.model_validate_json(result_path.read_text(encoding="utf-8"))
    if result.status != CanaryStatus.PATH_CHANGED:
        raise PromotionError("Only a PATH_CHANGED run can promote a replacement witness")
    if result.rescue is None or not result.rescue.passed:
        raise PromotionError("Run does not contain a deterministically verified Rescue")
    if result.known_path.canary_id != artifact.contract.id:
        raise PromotionError("Run result belongs to a different Canary")

    new_baseline = _resolve_commit(repo_path, result.known_path.pr_ref)

    # Re-verify the persisted replacement patch from scratch before mutating the
    # trusted artifact. This guards against edited or mismatched run evidence.
    with TemporaryDirectory(prefix="roadmap-canary-promote-") as temporary:
        workspace = Path(temporary) / "pr"
        create_worktree(repo_path, new_baseline, workspace)
        try:
            verification = replay_witness(
                workspace,
                replacement_path,
                artifact.contract,
                timeout_seconds=timeout_seconds,
            )
        finally:
            remove_worktree(repo_path, workspace)

    if not verification.passed:
        details = "; ".join(verification.errors) or "verification failed"
        raise PromotionError(
            "Persisted replacement witness no longer verifies on the PR state: " + details
        )

    previous_metadata = (
        artifact.metadata.model_dump(mode="json") if artifact.metadata is not None else None
    )
    previous_witness_hash = artifact.witness_digest

    witness_path = canary_path / "witness.patch"
    witness_path.write_text(replacement_path.read_text(encoding="utf-8"), encoding="utf-8")

    metadata = CanaryMetadata(
        canary_id=artifact.contract.id,
        baseline_commit=new_baseline,
        contract_hash=contract_hash(artifact.contract),
        witness_hash=sha256_file(witness_path),
        created_at=datetime.now(timezone.utc).isoformat(),
        created_by=f"verified-rescue:{result.rescue.agent}",
        status="valid",
    )
    (canary_path / "metadata.json").write_text(
        metadata.model_dump_json(indent=2),
        encoding="utf-8",
    )

    promotion_evidence = {
        "promoted_from_run": str(run_path),
        "pr_ref": result.known_path.pr_ref,
        "new_baseline_commit": new_baseline,
        "previous_witness_hash": previous_witness_hash,
        "previous_metadata": previous_metadata,
        "rescue_agent": result.rescue.agent,
        "rescue_task_id": result.rescue.task_id,
        "verification": json.loads(verification.model_dump_json()),
    }
    (canary_path / "evidence.json").write_text(
        json.dumps(promotion_evidence, indent=2),
        encoding="utf-8",
    )

    load_canary_artifact(canary_path)
    return canary_path
