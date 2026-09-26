from __future__ import annotations

import json
import subprocess
from pathlib import Path

from roadmap_canary.artifacts import load_canary_artifact
from roadmap_canary.capture import CaptureError, capture_canary


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
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


def _contract(path: Path, *, expected: str = "future-path") -> Path:
    contract = path / "contract.yaml"
    contract.write_text(
        f'''version: 1
id: issue-1
feature: demo-future-capability
must_prove:
  - witness.txt demonstrates the future path
verification:
  commands:
    - python -c "from pathlib import Path; assert Path('witness.txt').read_text().strip() == '{expected}'"
proof_budget:
  max_files_changed: 2
  max_added_lines: 5
  max_new_dependencies: 0
''',
        encoding="utf-8",
    )
    return contract


def test_capture_canary_verifies_and_writes_portable_artifact(tmp_path: Path) -> None:
    repo, base_sha, witness_sha = _repo(tmp_path)
    contract = _contract(tmp_path)
    output = tmp_path / "canary"

    result = capture_canary(
        repo,
        contract,
        base_ref=base_sha,
        witness_ref=witness_sha,
        output_dir=output,
    )

    assert result == output.resolve()
    artifact = load_canary_artifact(output)
    assert artifact.contract.id == "issue-1"
    assert artifact.metadata is not None
    assert artifact.metadata.baseline_commit == base_sha
    assert "witness.txt" in artifact.witness_path.read_text(encoding="utf-8")

    evidence = json.loads((output / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["baseline_commit"] == base_sha
    assert evidence["witness_commit"] == witness_sha
    assert evidence["verification"]["verification_passed"] is True


def test_capture_rejects_witness_that_does_not_satisfy_contract(tmp_path: Path) -> None:
    repo, base_sha, witness_sha = _repo(tmp_path)
    contract = _contract(tmp_path, expected="different-value")

    try:
        capture_canary(
            repo,
            contract,
            base_ref=base_sha,
            witness_ref=witness_sha,
            output_dir=tmp_path / "canary",
        )
    except CaptureError as exc:
        assert "not a valid executable proof" in str(exc)
    else:
        raise AssertionError("capture_canary should reject an invalid witness")
