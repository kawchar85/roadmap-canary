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
    metadata: CanaryMetadata

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
    """Load a trusted Canary artifact.

    Requires all four files: contract.yaml, witness.patch, metadata.json, evidence.json.
    metadata.json must be present and its hashes must match the actual files.
    A missing or malformed metadata.json is always a hard failure.
    """
    root = Path(path).resolve()
    contract_path = root / "contract.yaml"
    witness_path = root / "witness.patch"
    metadata_path = root / "metadata.json"

    if not contract_path.is_file():
        raise FileNotFoundError(f"Missing contract: {contract_path}")
    if not witness_path.is_file():
        raise FileNotFoundError(f"Missing witness: {witness_path}")
    if not metadata_path.is_file():
        raise FileNotFoundError(
            f"Missing metadata: {metadata_path}. "
            "Run 'roadmap-canary capture' to create a trusted artifact with provenance."
        )

    try:
        metadata = CanaryMetadata.model_validate(
            json.loads(metadata_path.read_text(encoding="utf-8"))
        )
    except Exception as exc:
        raise ValueError(f"Malformed metadata.json: {exc}") from exc

    artifact = CanaryArtifact(
        root=root,
        contract=load_contract(contract_path),
        witness_path=witness_path,
        metadata=metadata,
    )

    if metadata.contract_hash != artifact.contract_digest:
        raise ValueError(
            f"Canary metadata contract hash mismatch: "
            f"metadata={metadata.contract_hash!r} actual={artifact.contract_digest!r}"
        )
    if metadata.witness_hash != artifact.witness_digest:
        raise ValueError(
            f"Canary metadata witness hash mismatch: "
            f"metadata={metadata.witness_hash!r} actual={artifact.witness_digest!r}"
        )

    return artifact
