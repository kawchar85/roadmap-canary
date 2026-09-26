from pathlib import Path

import pytest
from pydantic import ValidationError

from roadmap_canary.contracts import contract_hash, load_contract


VALID_CONTRACT = """
version: 1
id: issue-1
feature: multiple-payment-providers
must_prove:
  - two interchangeable providers can satisfy the shared contract
verification:
  commands:
    - npm test
proof_budget:
  max_files_changed: 6
  max_added_lines: 120
  max_new_dependencies: 0
"""


def test_load_contract(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text(VALID_CONTRACT, encoding="utf-8")

    contract = load_contract(path)

    assert contract.id == "issue-1"
    assert contract.verification.commands == ["npm test"]


def test_contract_hash_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text(VALID_CONTRACT, encoding="utf-8")
    contract = load_contract(path)

    assert contract_hash(contract) == contract_hash(contract)
    assert len(contract_hash(contract)) == 64


def test_contract_rejects_empty_verification_commands(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text(
        VALID_CONTRACT.replace("    - npm test", "    - ''"),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_contract(path)
