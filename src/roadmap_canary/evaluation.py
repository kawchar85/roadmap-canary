from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from .artifacts import CanaryArtifact, load_canary_artifact
from .models import CanaryStatus, KnownPathCheck, ReplayResult
from .replay import replay_witness
from .worktree import create_worktree, remove_worktree


def classify_known_path(
    *,
    canary_id: str,
    feature: str,
    base_ref: str,
    pr_ref: str,
    base: ReplayResult,
    pr: ReplayResult,
) -> KnownPathCheck:
    """Classify BASE/PR witness replay before any Rescue attempt."""

    if base.passed and pr.passed:
        return KnownPathCheck(
            canary_id=canary_id,
            feature=feature,
            base_ref=base_ref,
            pr_ref=pr_ref,
            base=base,
            pr=pr,
            status=CanaryStatus.SAFE,
            rescue_required=False,
            reason="The previously demonstrated viability witness still verifies on the PR.",
        )

    if base.passed and not pr.passed:
        return KnownPathCheck(
            canary_id=canary_id,
            feature=feature,
            base_ref=base_ref,
            pr_ref=pr_ref,
            base=base,
            pr=pr,
            status=None,
            rescue_required=True,
            reason=(
                "The known witness verifies on BASE but not on the PR. "
                "Rescue is required before a roadmap verdict can be produced."
            ),
        )

    if not base.passed and not pr.passed:
        return KnownPathCheck(
            canary_id=canary_id,
            feature=feature,
            base_ref=base_ref,
            pr_ref=pr_ref,
            base=base,
            pr=pr,
            status=CanaryStatus.STALE,
            rescue_required=False,
            reason=(
                "The witness already fails on BASE, so the current PR cannot be blamed. "
                "The canary needs refresh or investigation."
            ),
        )

    return KnownPathCheck(
        canary_id=canary_id,
        feature=feature,
        base_ref=base_ref,
        pr_ref=pr_ref,
        base=base,
        pr=pr,
        status=CanaryStatus.SAFE,
        rescue_required=False,
        reason=(
            "The witness fails on BASE but verifies on the PR. "
            "The PR restores this demonstrated path; no roadmap regression is indicated."
        ),
    )


def _replay_ref(
    repo: Path,
    ref: str,
    destination: Path,
    artifact: CanaryArtifact,
    *,
    timeout_seconds: int,
) -> ReplayResult:
    create_worktree(repo, ref, destination)
    try:
        return replay_witness(
            destination,
            artifact.witness_path,
            artifact.contract,
            timeout_seconds=timeout_seconds,
        )
    finally:
        remove_worktree(repo, destination)


def check_known_path(
    repo: str | Path,
    canary: str | Path,
    *,
    base_ref: str,
    pr_ref: str,
    timeout_seconds: int = 300,
) -> KnownPathCheck:
    """Replay one stored witness against BASE and PR in isolated worktrees."""

    repo_path = Path(repo).resolve()
    artifact = load_canary_artifact(canary)

    with TemporaryDirectory(prefix="roadmap-canary-") as temporary:
        root = Path(temporary)
        base_result = _replay_ref(
            repo_path,
            base_ref,
            root / "base",
            artifact,
            timeout_seconds=timeout_seconds,
        )
        pr_result = _replay_ref(
            repo_path,
            pr_ref,
            root / "pr",
            artifact,
            timeout_seconds=timeout_seconds,
        )

    return classify_known_path(
        canary_id=artifact.contract.id,
        feature=artifact.contract.feature,
        base_ref=base_ref,
        pr_ref=pr_ref,
        base=base_result,
        pr=pr_result,
    )
