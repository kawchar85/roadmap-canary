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

The deterministic core is now working and covered by CI:

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
- prepared-patch Rescue adapter for engine testing
- deterministic `PATH_CHANGED` and `ROADMAP_RISK` end-to-end flows
- JSON-serializable result models

IBM Bob will replace the prepared-patch Rescue adapter once the Bob integration spike is complete. The verifier remains independent from Bob.

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

For development, run one prepared Rescue patch through the same deterministic verifier:

```bash
roadmap-canary check \
  --repo /path/to/target-repo \
  --canary /path/to/.roadmap-canary/issue-1 \
  --base <base-ref> \
  --pr <pr-ref> \
  --rescue-patch /path/to/alternate-proof.patch
```

Add `--json` to the check commands for machine-readable output.

## Result semantics

- `SAFE`: the known executable path still verifies on the PR.
- `PATH_CHANGED`: the known path disappeared, but Rescue produced another deterministically verified path.
- `ROADMAP_RISK`: the known path disappeared and no Rescue candidate passed deterministic verification within the configured attempt.
- `STALE`: the witness already fails on BASE, so the PR cannot be blamed.

A `ROADMAP_RISK` result does **not** claim that the future capability is impossible. It means its previously demonstrated viability is no longer established by the bounded Rescue process.

## Design specification

The working design specification is kept temporarily under `docs/design/`. It can be removed once the implementation and final project documentation supersede it.
