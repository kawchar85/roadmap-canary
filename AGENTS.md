# Roadmap Canary Engineering Instructions

## Product invariant

Roadmap Canary must separate agent reasoning from deterministic verification.

- IBM Bob may inspect, reason, and propose candidate code.
- Bob must not decide the final SAFE / PATH_CHANGED / ROADMAP_RISK / STALE result.
- Final status must come from executable evidence and deterministic checks.

## Core semantics

- `SAFE`: the existing witness verifies on the PR.
- `PATH_CHANGED`: the old witness fails on the PR, but Rescue produces a replacement proof that verifies.
- `ROADMAP_RISK`: the witness verifies on BASE, fails on PR, and no replacement proof verifies within the configured Rescue budget.
- `STALE`: the witness does not verify on BASE, so the current PR cannot be blamed.

A Rescue failure never proves the future capability is impossible. It only means replacement viability was not demonstrated within the configured bounded search.

## Engineering rules

- Keep speculative work isolated in Git worktrees.
- Never modify the user's active working tree during replay or Rescue.
- Treat Future Contracts as human-approved trusted configuration.
- Preserve evidence for every deterministic check.
- Prefer small, testable modules over framework-heavy abstractions.
- Do not add dashboard or GitHub App complexity before the core replay/verification path works.
