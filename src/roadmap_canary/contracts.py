from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from .models import FutureContract


def load_contract(path: str | Path) -> FutureContract:
    contract_path = Path(path)
    raw = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Future Contract must be a YAML mapping")
    return FutureContract.model_validate(raw)


def contract_hash(contract: FutureContract) -> str:
    canonical = json.dumps(
        contract.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
