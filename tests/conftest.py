"""Shared test helpers for Roadmap Canary tests."""
from __future__ import annotations

import json
from pathlib import Path

from roadmap_canary.artifacts import sha256_file
from roadmap_canary.contracts import contract_hash, load_contract
from roadmap_canary.models import CanaryMetadata


def write_canary_metadata(canary_dir: Path, *, baseline_commit: str = "test-baseline") -> None:
    """Write a valid metadata.json alongside an existing contract.yaml + witness.patch.

    Called from tests that need a complete trusted artifact after manually writing
    the two core files but before calling load_canary_artifact / check_known_path /
    check_canary.
    """
    contract_path = canary_dir / "contract.yaml"
    witness_path = canary_dir / "witness.patch"

    contract = load_contract(contract_path)
    metadata = CanaryMetadata(
        canary_id=contract.id,
        baseline_commit=baseline_commit,
        contract_hash=contract_hash(contract),
        witness_hash=sha256_file(witness_path),
        created_at="2024-01-01T00:00:00+00:00",
        created_by="test-helper",
        status="valid",
    )
    (canary_dir / "metadata.json").write_text(
        json.dumps(metadata.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
