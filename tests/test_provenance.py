"""Provenance regression tests for Roadmap Canary artifact integrity.

Covers:
  A. Missing metadata.json → trusted artifact load fails clearly
  B. Contract tampering → contract hash mismatch → artifact rejected
  C. Witness tampering → witness hash mismatch → artifact rejected
  D. Valid captured artifact → loads and verifies successfully
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from roadmap_canary.artifacts import load_canary_artifact, sha256_file
from roadmap_canary.capture import capture_canary
from roadmap_canary.contracts import contract_hash, load_contract
from roadmap_canary.models import CanaryMetadata

from conftest import write_canary_metadata


# ---------------------------------------------------------------------------
# Minimal contract / witness helpers
# ---------------------------------------------------------------------------

CONTRACT_YAML = """\
version: 1
id: provenance-test
feature: provenance-regression-fixture
must_prove:
  - witness.txt demonstrates the future path
verification:
  commands:
    - python3 -c "from pathlib import Path; assert Path('witness.txt').read_text().strip() == 'future-path'"
proof_budget:
  max_files_changed: 2
  max_added_lines: 5
  max_new_dependencies: 0
"""

WITNESS_PATCH = """\
diff --git a/witness.txt b/witness.txt
new file mode 100644
--- /dev/null
+++ b/witness.txt
@@ -0,0 +1 @@
+future-path
"""


def _write_base_artifact(canary_dir: Path) -> None:
    """Write contract.yaml and witness.patch (no metadata yet)."""
    canary_dir.mkdir(parents=True, exist_ok=True)
    (canary_dir / "contract.yaml").write_text(CONTRACT_YAML, encoding="utf-8")
    (canary_dir / "witness.patch").write_text(WITNESS_PATCH, encoding="utf-8")


# ---------------------------------------------------------------------------
# A. Missing metadata
# ---------------------------------------------------------------------------


def test_missing_metadata_fails_clearly(tmp_path: Path) -> None:
    """Artifact without metadata.json must be rejected with a clear error."""
    canary = tmp_path / "canary"
    _write_base_artifact(canary)
    # No metadata.json written.

    with pytest.raises(FileNotFoundError, match="Missing metadata"):
        load_canary_artifact(canary)


# ---------------------------------------------------------------------------
# B. Contract tampering
# ---------------------------------------------------------------------------


def test_contract_tampering_fails_hash_check(tmp_path: Path) -> None:
    """Modifying contract.yaml after capture must cause a contract hash mismatch error."""
    canary = tmp_path / "canary"
    _write_base_artifact(canary)
    write_canary_metadata(canary)

    # Tamper with contract.yaml by adding a new must_prove entry.
    # (YAML comments don't change the parsed model; altering the data does.)
    tampered = CONTRACT_YAML.replace(
        "  - witness.txt demonstrates the future path",
        "  - witness.txt demonstrates the future path\n  - additional tampered constraint",
    )
    (canary / "contract.yaml").write_text(tampered, encoding="utf-8")

    with pytest.raises(ValueError, match="contract hash mismatch"):
        load_canary_artifact(canary)


# ---------------------------------------------------------------------------
# C. Witness tampering
# ---------------------------------------------------------------------------


def test_witness_tampering_fails_hash_check(tmp_path: Path) -> None:
    """Modifying witness.patch after capture must cause a witness hash mismatch error."""
    canary = tmp_path / "canary"
    _write_base_artifact(canary)
    write_canary_metadata(canary)

    # Tamper with witness.patch after metadata was captured.
    (canary / "witness.patch").write_text(
        WITNESS_PATCH + "\n# tampered\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="witness hash mismatch"):
        load_canary_artifact(canary)


# ---------------------------------------------------------------------------
# D. Valid captured artifact (via real capture workflow)
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _build_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """Create a minimal git repo with a base commit and a witness commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Roadmap Canary Test")

    (repo / "base.txt").write_text("baseline\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")

    (repo / "witness.txt").write_text("future-path\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "witness")
    witness_sha = _git(repo, "rev-parse", "HEAD")

    return repo, base_sha, witness_sha


def test_valid_captured_artifact_loads_successfully(tmp_path: Path) -> None:
    """A real capture workflow must produce an artifact that loads and verifies cleanly."""
    repo, base_sha, witness_sha = _build_repo(tmp_path)

    contract_file = tmp_path / "contract.yaml"
    contract_file.write_text(CONTRACT_YAML, encoding="utf-8")

    output = tmp_path / "canary"
    result_path = capture_canary(
        repo,
        contract_file,
        base_ref=base_sha,
        witness_ref=witness_sha,
        output_dir=output,
    )

    artifact = load_canary_artifact(result_path)
    assert artifact.contract.id == "provenance-test"
    assert artifact.metadata.baseline_commit == base_sha
    assert artifact.metadata.contract_hash == artifact.contract_digest
    assert artifact.metadata.witness_hash == artifact.witness_digest


def test_malformed_metadata_fails_clearly(tmp_path: Path) -> None:
    """A metadata.json that cannot be parsed must fail with a clear error."""
    canary = tmp_path / "canary"
    _write_base_artifact(canary)
    (canary / "metadata.json").write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed metadata"):
        load_canary_artifact(canary)


def test_metadata_wrong_canary_id_is_rejected(tmp_path: Path) -> None:
    """metadata.json with wrong contract hash (e.g. from a different canary) is rejected."""
    canary = tmp_path / "canary"
    _write_base_artifact(canary)

    # Write metadata with a wrong contract_hash
    bad_metadata = {
        "canary_id": "provenance-test",
        "baseline_commit": "abc123",
        "contract_hash": "0" * 64,  # wrong hash
        "witness_hash": sha256_file(canary / "witness.patch"),
    }
    (canary / "metadata.json").write_text(json.dumps(bad_metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="contract hash mismatch"):
        load_canary_artifact(canary)
