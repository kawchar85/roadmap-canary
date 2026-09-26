# Roadmap Canary

**Regression testing for software you haven't built yet.**

Roadmap Canary maintains executable evidence that an accepted future capability still has at least one demonstrated viable path through an evolving codebase.

## Core idea

Traditional CI asks whether today's software still works. Roadmap Canary adds a second question: does an accepted future capability still have a demonstrated executable path?

The engine stores a human-approved Future Contract and a disposable witness patch. It replays that witness on BASE and PR states, verifies it with deterministic checks, and only invokes Rescue when a previously demonstrated path disappears.

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

## Current implementation stage

The repository is currently building the deterministic foundation first:

1. Future Contract schema and validation
2. Canary artifact loading and hashing
3. isolated Git worktrees
4. witness replay
5. deterministic command verification

IBM Bob Rescue is intentionally integrated after this foundation is stable.

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

## Design specification

The working design specification is kept temporarily under `docs/design/`. It can be removed once the implementation and final project documentation supersede it.
