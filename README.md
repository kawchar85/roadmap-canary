# Roadmap Canary

**Regression testing for software you haven't built yet.**

Roadmap Canary maintains executable evidence that an accepted future capability still has at least one demonstrated viable path through an evolving codebase.

## Core idea

Traditional CI asks whether today's software still works. Roadmap Canary adds a second question: does an accepted future capability still have a demonstrated executable path?

The engine stores a human-approved Future Contract and a disposable witness patch. It replays that witness on BASE and PR states, verifies it with deterministic checks, and invokes Rescue only when a previously demonstrated path disappears.

```text
Future Contract
      +
Witness Patch
      |
      v
BASE replay ---- PR replay
                   |
              witness fails
                   |
                 Rescue
                   |
         deterministic verification
              /          \
    PATH CHANGED      ROADMAP RISK
```

## Current implementation

The core engine now includes:

- strict Future Contract parsing and hashing
- canary artifact integrity checks
- isolated Git worktrees for BASE, PR, and Rescue
- witness replay using `git apply --index`
- deterministic verification commands
- protected-test integrity checks
- proof-budget enforcement
- npm dependency-addition checks
- BASE/PR classification
- `SAFE`, `STALE`, and Rescue-required states
- Rescue-agent abstraction
- IBM Bob Shell Rescue adapter
- prepared-patch Rescue adapter for deterministic testing
- deterministic `PATH_CHANGED` and `ROADMAP_RISK` end-to-end flows
- structured `result.json` evidence
- verified replacement-witness patch persistence

The central invariant is:

> **Bob proposes. Roadmap Canary verifies.**

IBM Bob may inspect the repository and create a candidate replacement proof inside an isolated Rescue worktree. Bob never decides the final Roadmap Canary status. Tests, protected-file checks, proof budgets, and other deterministic evidence decide whether the candidate verifies.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

Validate a Future Contract:

```bash
roadmap-canary validate examples/issue-1/contract.yaml
```

Replay a stored witness on BASE and PR without Rescue:

```bash
roadmap-canary check-known-path \
  --repo /path/to/target-repo \
  --canary /path/to/.roadmap-canary/issue-1 \
  --base <base-ref> \
  --pr <pr-ref>
```

Run the full flow with IBM Bob Rescue:

```bash
export BOB_API_KEY="..."

roadmap-canary check \
  --repo /path/to/target-repo \
  --canary /path/to/.roadmap-canary/issue-1 \
  --base <base-ref> \
  --pr <pr-ref> \
  --bob-max-turns 8 \
  --output-dir ./run-evidence
```

For deterministic development, a prepared alternate proof can replace Bob:

```bash
roadmap-canary check \
  --repo /path/to/target-repo \
  --canary /path/to/.roadmap-canary/issue-1 \
  --base <base-ref> \
  --pr <pr-ref> \
  --rescue-patch /path/to/alternate-proof.patch
```

Add `--json` to the check commands for machine-readable output.

## IBM Bob integration

The hackathon integration has been experimentally verified with Bob Shell `2.0.5` using:

- API-key authentication
- non-interactive `bob run`
- explicit `--workspace`
- `agent` mode
- JSON output
- bounded `--max-turns`
- direct file modification inside a temporary Git repository

See `docs/bob-integration.md` for the verified integration behavior and the important handling required for agent-created untracked files.

## Result semantics

- `SAFE`: the known executable path still verifies on the PR.
- `PATH_CHANGED`: the known path disappeared, but Rescue produced another deterministically verified path.
- `ROADMAP_RISK`: the known path disappeared and no Rescue candidate passed deterministic verification within the configured attempt.
- `STALE`: the witness already fails on BASE, so the PR cannot be blamed.

A `ROADMAP_RISK` result does **not** claim that the future capability is impossible. It means its previously demonstrated viability is no longer established by the bounded Rescue process.

## Design specification

The working design specification is kept temporarily under `docs/design/`. It can be removed once the implementation and final project documentation supersede it.
