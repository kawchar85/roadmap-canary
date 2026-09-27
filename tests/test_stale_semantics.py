"""STALE-semantics regression tests for classify_known_path.

Verified matrix:

  BASE PASS + CHANGE PASS → SAFE
  BASE PASS + CHANGE FAIL → Rescue required (status=None, rescue_required=True)
  BASE FAIL + CHANGE FAIL → STALE (rescue_required=False)
  BASE FAIL + CHANGE PASS → STALE (rescue_required=False)

Rationale: if the known proof does not work on BASE, Roadmap Canary cannot
attribute the regression to the proposed change, so no Rescue attempt is made.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from roadmap_canary.evaluation import classify_known_path
from roadmap_canary.models import CanaryStatus, ReplayResult


def _result(tmp_path: Path, passed: bool) -> ReplayResult:
    return ReplayResult(
        workspace=tmp_path,
        patch_applied=passed,
        verification_passed=passed,
    )


def test_base_pass_change_pass_is_safe(tmp_path: Path) -> None:
    """BASE PASS + CHANGE PASS → SAFE, no Rescue."""
    result = classify_known_path(
        canary_id="issue-1",
        feature="future-feature",
        base_ref="base",
        pr_ref="pr",
        base=_result(tmp_path / "base", True),
        pr=_result(tmp_path / "pr", True),
    )

    assert result.status == CanaryStatus.SAFE
    assert not result.rescue_required


def test_base_pass_change_fail_requires_rescue(tmp_path: Path) -> None:
    """BASE PASS + CHANGE FAIL → Rescue required, status deferred until Rescue completes."""
    result = classify_known_path(
        canary_id="issue-1",
        feature="future-feature",
        base_ref="base",
        pr_ref="pr",
        base=_result(tmp_path / "base", True),
        pr=_result(tmp_path / "pr", False),
    )

    assert result.status is None
    assert result.rescue_required


def test_base_fail_change_fail_is_stale(tmp_path: Path) -> None:
    """BASE FAIL + CHANGE FAIL → STALE, no Rescue attempted."""
    result = classify_known_path(
        canary_id="issue-1",
        feature="future-feature",
        base_ref="base",
        pr_ref="pr",
        base=_result(tmp_path / "base", False),
        pr=_result(tmp_path / "pr", False),
    )

    assert result.status == CanaryStatus.STALE
    assert not result.rescue_required


def test_base_fail_change_pass_is_stale(tmp_path: Path) -> None:
    """BASE FAIL + CHANGE PASS → STALE, not SAFE.

    Even if the PR witness passes, the stored Canary is not a valid known-good
    baseline.  We cannot attribute any regression (or restoration) to the PR.
    Rescue must not be invoked.
    """
    result = classify_known_path(
        canary_id="issue-1",
        feature="future-feature",
        base_ref="base",
        pr_ref="pr",
        base=_result(tmp_path / "base", False),
        pr=_result(tmp_path / "pr", True),
    )

    assert result.status == CanaryStatus.STALE
    assert not result.rescue_required


def test_base_fail_change_pass_rescue_not_invoked(tmp_path: Path) -> None:
    """BASE FAIL + CHANGE PASS must not set rescue_required=True.

    Rescue is only triggered when BASE PASS + CHANGE FAIL.  A BASE failure
    means the stored proof does not hold on the known-good reference, so
    Rescue cannot meaningfully attribute the change.
    """
    result = classify_known_path(
        canary_id="issue-1",
        feature="future-feature",
        base_ref="base",
        pr_ref="pr",
        base=_result(tmp_path / "base", False),
        pr=_result(tmp_path / "pr", True),
    )

    # Rescue must NOT be triggered for any BASE failure case.
    assert not result.rescue_required
    assert result.status == CanaryStatus.STALE
