from datetime import date

from roadmap_canary.evaluation import lifecycle_stale_reason
from roadmap_canary.models import FutureContract


def _contract(expires: str | None) -> FutureContract:
    commitment = {"state": "committed", "blocking_policy": "advisory"}
    if expires is not None:
        commitment["expires"] = expires

    return FutureContract.model_validate(
        {
            "version": 1,
            "id": "issue-1",
            "feature": "future-capability",
            "commitment": commitment,
            "must_prove": ["proof exists"],
            "verification": {"commands": ["true"]},
            "proof_budget": {
                "max_files_changed": 1,
                "max_added_lines": 10,
                "max_new_dependencies": 0,
            },
        }
    )


def test_expired_contract_is_stale() -> None:
    reason = lifecycle_stale_reason(
        _contract("2026-09-25"),
        today=date(2026, 9, 26),
    )
    assert reason == "Future Contract expired on 2026-09-25."


def test_contract_expiring_today_is_still_active() -> None:
    assert (
        lifecycle_stale_reason(
            _contract("2026-09-26"),
            today=date(2026, 9, 26),
        )
        is None
    )
