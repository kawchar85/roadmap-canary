from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from .artifacts import CanaryArtifact, load_canary_artifact
from .models import (
    CanaryCheck,
    CanaryStatus,
    FutureContract,
    KnownPathCheck,
    ReplayResult,
    RescueResult,
)
from .replay import replay_witness, verify_candidate_workspace
from .rescue import RescueAgent
from .verifier import snapshot_protected_files
from .worktree import (
    create_worktree,
    git_diff,
    remove_worktree,
    stage_all_changes,
)


def lifecycle_stale_reason(
    contract: FutureContract,
    *,
    today: date | None = None,
) -> str | None:
    """Return a deterministic lifecycle reason when a Canary is no longer active."""

    expires = contract.commitment.expires
    current = today or date.today()
    if expires is not None and expires < current:
        return f"Future Contract expired on {expires.isoformat()}."
    return None


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

    stale_reason = lifecycle_stale_reason(artifact.contract)
    if stale_reason is not None:
        return KnownPathCheck(
            canary_id=artifact.contract.id,
            feature=artifact.contract.feature,
            base_ref=base_ref,
            pr_ref=pr_ref,
            base=base_result,
            pr=pr_result,
            status=CanaryStatus.STALE,
            rescue_required=False,
            reason=stale_reason + " The Canary must be reviewed or renewed before PR attribution.",
        )

    return classify_known_path(
        canary_id=artifact.contract.id,
        feature=artifact.contract.feature,
        base_ref=base_ref,
        pr_ref=pr_ref,
        base=base_result,
        pr=pr_result,
    )


def _rescue_result_from_agent_run(
    agent_run,
    *,
    candidate_produced: bool,
    verification: ReplayResult | None = None,
    candidate_patch: str | None = None,
) -> RescueResult:
    return RescueResult(
        attempted=True,
        agent=agent_run.agent,
        candidate_produced=candidate_produced,
        verification=verification,
        candidate_patch=candidate_patch,
        task_id=agent_run.task_id,
        duration_ms=agent_run.duration_ms,
        cost=agent_run.cost,
        tool_calls=agent_run.tool_calls,
        last_message=agent_run.last_message,
        errors=agent_run.errors,
    )


def check_canary(
    repo: str | Path,
    canary: str | Path,
    *,
    base_ref: str,
    pr_ref: str,
    rescue_agent: RescueAgent,
    timeout_seconds: int = 300,
    known_path: KnownPathCheck | None = None,
) -> CanaryCheck:
    """Run known-path replay and, when required, one bounded Rescue attempt.

    ``known_path`` may be supplied by callers that already replayed BASE and PR,
    such as the web UI. This avoids repeating the same deterministic work before
    Rescue while preserving the original behavior for CLI and other callers.
    """

    if known_path is None:
        known_path = check_known_path(
            repo,
            canary,
            base_ref=base_ref,
            pr_ref=pr_ref,
            timeout_seconds=timeout_seconds,
        )
    elif known_path.base_ref != base_ref or known_path.pr_ref != pr_ref:
        raise ValueError("known_path refs do not match the requested BASE/PR refs")

    if not known_path.rescue_required:
        status = known_path.status or CanaryStatus.SAFE
        return CanaryCheck(
            known_path=known_path,
            status=status,
            reason=known_path.reason,
        )

    repo_path = Path(repo).resolve()
    artifact = load_canary_artifact(canary)
    if artifact.contract.id != known_path.canary_id:
        raise ValueError("known_path does not belong to the selected Canary")

    with TemporaryDirectory(prefix="roadmap-canary-rescue-") as temporary:
        rescue_workspace = Path(temporary) / "rescue"
        create_worktree(repo_path, pr_ref, rescue_workspace)
        try:
            protected_snapshot = snapshot_protected_files(
                rescue_workspace,
                artifact.contract,
            )
            agent_run = rescue_agent.rescue(
                rescue_workspace,
                artifact.contract,
                known_path.pr,
            )

            if not agent_run.candidate_produced:
                rescue = _rescue_result_from_agent_run(
                    agent_run,
                    candidate_produced=False,
                )
                return CanaryCheck(
                    known_path=known_path,
                    rescue=rescue,
                    status=CanaryStatus.ROADMAP_RISK,
                    reason=(
                        "The previous demonstrated path was lost and the Rescue attempt "
                        "did not produce a candidate replacement proof. Viability is no "
                        "longer demonstrated within this Rescue attempt."
                    ),
                )

            # Normalize agent-created tracked and untracked files before measuring
            # the candidate. Verification may create additional files, so normalize
            # once more before preserving the final replacement patch.
            stage_all_changes(rescue_workspace)
            verification = verify_candidate_workspace(
                rescue_workspace,
                artifact.contract,
                protected_snapshot,
                timeout_seconds=timeout_seconds,
            )
            stage_all_changes(rescue_workspace)
            candidate_patch = git_diff(rescue_workspace)
            rescue = _rescue_result_from_agent_run(
                agent_run,
                candidate_produced=True,
                verification=verification,
                candidate_patch=candidate_patch,
            )

            if rescue.passed:
                return CanaryCheck(
                    known_path=known_path,
                    rescue=rescue,
                    status=CanaryStatus.PATH_CHANGED,
                    reason=(
                        "The previous witness no longer works, but Rescue produced a new "
                        "candidate that passed deterministic verification. The capability "
                        "still has a demonstrated viable path."
                    ),
                )

            return CanaryCheck(
                known_path=known_path,
                rescue=rescue,
                status=CanaryStatus.ROADMAP_RISK,
                reason=(
                    "The previous demonstrated path was lost and the Rescue candidate did "
                    "not pass deterministic verification. Viability is no longer "
                    "demonstrated within this Rescue attempt."
                ),
            )
        finally:
            remove_worktree(repo_path, rescue_workspace)
