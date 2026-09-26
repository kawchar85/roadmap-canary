from __future__ import annotations

from pathlib import Path

from .models import CanaryCheck


def persist_run(result: CanaryCheck, output_dir: str | Path) -> Path:
    """Persist structured run evidence and any verified Rescue replacement patch."""

    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)

    result_path = root / "result.json"
    result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    if (
        result.rescue is not None
        and result.rescue.passed
        and result.rescue.candidate_patch
    ):
        (root / "replacement-witness.patch").write_text(
            result.rescue.candidate_patch,
            encoding="utf-8",
        )

    return root
