from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CanaryStatus(StrEnum):
    SAFE = "SAFE"
    PATH_CHANGED = "PATH_CHANGED"
    ROADMAP_RISK = "ROADMAP_RISK"
    STALE = "STALE"


class Commitment(StrictModel):
    state: str = "committed"
    target: str | None = None
    expires: str | None = None
    blocking_policy: Literal["advisory", "blocking"] = "advisory"


class ContractSource(StrictModel):
    type: str
    repository: str | None = None
    issue: int | None = None
    reference: str | None = None


class ProtectedSurfaces(StrictModel):
    paths: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    infrastructure: list[str] = Field(default_factory=list)


class VerificationConfig(StrictModel):
    commands: list[str] = Field(min_length=1)

    @field_validator("commands")
    @classmethod
    def commands_must_be_nonempty(cls, value: list[str]) -> list[str]:
        if any(not command.strip() for command in value):
            raise ValueError("verification commands cannot be empty")
        return value


class ProofBudget(StrictModel):
    max_files_changed: int = Field(ge=0)
    max_added_lines: int = Field(ge=0)
    max_new_dependencies: int = Field(default=0, ge=0)


class FutureContract(StrictModel):
    version: Literal[1] = 1
    id: str = Field(min_length=1)
    feature: str = Field(min_length=1)
    source: ContractSource | None = None
    commitment: Commitment = Field(default_factory=Commitment)
    must_prove: list[str] = Field(min_length=1)
    must_not: list[str] = Field(default_factory=list)
    protected_surfaces: ProtectedSurfaces = Field(default_factory=ProtectedSurfaces)
    protected_tests: list[str] = Field(default_factory=list)
    verification: VerificationConfig
    proof_budget: ProofBudget


class CommandResult(StrictModel):
    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = Field(ge=0)

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


class DiffStats(StrictModel):
    files_changed: int = Field(ge=0)
    added_lines: int = Field(ge=0)
    removed_lines: int = Field(ge=0)
    new_dependencies: int = Field(ge=0)
    changed_paths: list[str] = Field(default_factory=list)


class BudgetResult(StrictModel):
    passed: bool
    stats: DiffStats
    violations: list[str] = Field(default_factory=list)


class ReplayResult(StrictModel):
    workspace: Path
    patch_applied: bool
    verification_passed: bool
    commands: list[CommandResult] = Field(default_factory=list)
    protected_tests_unchanged: bool = True
    changed_protected_tests: list[str] = Field(default_factory=list)
    budget: BudgetResult | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        budget_passed = self.budget is None or self.budget.passed
        return (
            self.patch_applied
            and self.verification_passed
            and self.protected_tests_unchanged
            and budget_passed
        )


class KnownPathCheck(StrictModel):
    canary_id: str
    feature: str
    base_ref: str
    pr_ref: str
    base: ReplayResult
    pr: ReplayResult
    status: CanaryStatus | None = None
    rescue_required: bool
    reason: str


class RescueRun(StrictModel):
    agent: str
    candidate_produced: bool
    errors: list[str] = Field(default_factory=list)


class RescueResult(StrictModel):
    attempted: bool
    agent: str
    candidate_produced: bool
    verification: ReplayResult | None = None
    candidate_patch: str | None = None
    errors: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.attempted
            and self.candidate_produced
            and self.verification is not None
            and self.verification.passed
        )


class CanaryCheck(StrictModel):
    known_path: KnownPathCheck
    rescue: RescueResult | None = None
    status: CanaryStatus
    reason: str


class CanaryMetadata(StrictModel):
    canary_id: str
    baseline_commit: str
    contract_hash: str
    witness_hash: str
    created_at: str | None = None
    created_by: str | None = None
    status: str = "valid"
