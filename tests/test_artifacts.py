import json
from pathlib import Path

from roadmap_canary.artifacts import load_canary_artifact, sha256_file


CONTRACT = """
version: 1
id: issue-1
feature: multiple-payment-providers
must_prove:
  - a second provider can use the real checkout path
verification:
  commands:
    - npm test
proof_budget:
  max_files_changed: 6
  max_added_lines: 120
  max_new_dependencies: 0
"""


def test_load_canary_artifact(tmp_path: Path) -> None:
    (tmp_path / "contract.yaml").write_text(CONTRACT, encoding="utf-8")
    (tmp_path / "witness.patch").write_text("demo patch", encoding="utf-8")
    witness_hash = sha256_file(tmp_path / "witness.patch")

    metadata = {
        "canary_id": "issue-1",
        "baseline_commit": "abc123",
        "contract_hash": "placeholder",
        "witness_hash": witness_hash,
    }
    (tmp_path / "metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    artifact = load_canary_artifact(tmp_path)

    assert artifact.contract.id == "issue-1"
    assert artifact.witness_digest == witness_hash
    assert artifact.metadata is not None
    assert artifact.metadata.baseline_commit == "abc123"
