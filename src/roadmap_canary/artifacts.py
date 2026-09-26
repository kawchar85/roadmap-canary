from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .contracts import contract_hash, load_contract
from .models import CanaryMetadata, FutureContract


@dataclass(frozen=True)
class CanaryArtifact:
    root: Path
    contract: FutureContract
    witness_path: Path
    metadata: CanaryMetadata | None

    @property
    def contract_digest(self) -> str:
        return contract_hash(self.contract)

    @property
    def witness_digest(self) -> str:
        return sha256_file(self.witness_path)


def sha256_file(path: str | Path) -> str:
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_canary_artifact(path: str | Path) -> CanaryArtifact:
    root = Path(path)
    contract_path = root / "contract.yaml"
    witness_path = root / "witness.patch"
    metadata_path = root / "metadata.json"

    if not contract_path.is_file():
        raise FileNotFoundError(f"Missing contract: {contract_path}")
    if not witness_path.is_file():
        raise FileNotFoundError(f"Missing witness: {witness_path}")

    metadata = None
    if metadata_path.is_file():
        metadata = CanaryMetadata.model_validate(
            json.loads(metadata_path.read_text(encoding="utf-8"))
        )

    return CanaryArtifact(
        root=root,
        contract=load_contract(contract_path),
        witness_path=witness_path,
        metadata=metadata,
    )
