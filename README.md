# Roadmap Canary

**Regression testing for software you haven't built yet.**

Roadmap Canary maintains executable evidence that an accepted future capability still has at least one demonstrated viable path through an evolving codebase.

## Core idea

Traditional CI asks whether today's software still works. Roadmap Canary adds a second question: does an accepted future capability still have a demonstrated executable path?

The engine stores a human-approved Future Contract and a disposable witness patch. It replays that witness on BASE and PR states, verifies it with deterministic checks, and invokes Rescue only when a previously demonstrated path disappears.

```text
accepted future capability
          |
          v
human-approved Future Contract
          +
verified disposable witness
          |
          v
BASE replay -------- PR replay
                       |
                  witness fails
                       |
                 bounded Rescue
                       |
                    IBM Bob
                       |
                candidate proof
                       |
          deterministic verification
                 /             \
       PATH CHANGED         ROADMAP RISK
          - SAFE
```

The central invariant is:

> **Bob proposes. Roadmap Canary verifies.**

IBM Bob may inspect the repository and create a candidate replacement proof inside an isolated Rescue worktree. Bob never decides the final Roadmap Canary status. Executable checks, protected-test integrity, proof budgets, and other approved evidence determine whether the candidate verifies.

## Current implementation

The core engine includes:

- strict Future Contract parsing and canonical hashing
- verified Canary capture from a BASE ref and witness ref
- Canary artifact integrity checks
- isolated Git worktrees for BASE, PR, and Rescue
- witness replay using `git apply --index`
- deterministic verification commands
- protected-test integrity checks
- proof-budget enforcement
- npm dependency-addition checks
- BASE/PR classification
- `SAFE`, `PATH_CHANGED`, `ROADMAP_RISK`, and `STALE` semantics
- Future Contract expiry handling
- Rescue-agent abstraction
- IBM Bob Shell Rescue adapter
- bounded Bob turns, Bobcoin cost, and wall-clock time
- MCP and subagents disabled by default during Rescue
- prepared-patch Rescue adapter for deterministic testing
- structured `result.json` evidence
- verified replacement-witness patch persistence
- explicit human-triggered promotion of a successful replacement witness

## Quick start

Each teammate or reviewer should use their own IBM Bob API key. Never commit or share `BOB_API_KEY`.

```bash
git clone git@github.com:kawchar85/roadmap-canary.git
cd roadmap-canary

pip install -e '.[dev]'

export BOB_API_KEY="THEIR_OWN_KEY"

roadmap-canary ui
```

The UI accepts a repository in `owner/repo` form. Roadmap Canary clones managed GitHub repositories over HTTPS, so inspecting a public target repository does not require GitHub SSH configuration. Private repositories require suitable HTTPS Git credentials, or you can use the **Use local repository** option.

IBM Bob is only invoked when the known future-capability witness no longer works on the selected change and Rescue is required.

## Canary artifact

A Canary is a small portable evidence bundle:

```text
.roadmap-canary/
  issue-1/
    contract.yaml
    witness.patch
    metadata.json
    evidence.json
```

`contract.yaml` is human-approved. `witness.patch` is disposable proof code, not production implementation. `metadata.json` binds the artifact to its hashes and baseline. `evidence.json` records capture or promotion evidence.

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

### 1. Capture the initial Canary

Once a witness implementation exists on a separate Git ref, Roadmap Canary derives the patch from BASE to that ref, replays it on a clean BASE worktree, and refuses to create the trusted artifact unless it passes deterministic verification.

```bash
roadmap-canary capture \
  --repo /path/to/target-repo \
  --contract examples/issue-1/contract.yaml \
  --base main \
  --witness canary/multi-provider-witness \
  --output /path/to/.roadmap-canary/issue-1
```

### 2. Replay the known path on BASE and PR

```bash
roadmap-canary check-known-path \
  --repo /path/to/target-repo \
  --canary /path/to/.roadmap-canary/issue-1 \
  --base <base-ref> \
  --pr <pr-ref>
```

### 3. Run the full flow with IBM Bob Rescue

Keep `BOB_API_KEY` in the local environment; never commit it.

```bash
roadmap-canary check \
  --repo /path/to/target-repo \
  --canary /path/to/.roadmap-canary/issue-1 \
  --base <base-ref> \
  --pr <pr-ref> \
  --bob-max-turns 8 \
  --bob-max-cost 0.50 \
  --bob-timeout 600 \
  --output-dir ./run-evidence
```

When the old witness still works, no Rescue is needed. When the old witness fails, Bob receives the approved Future Contract and failure evidence, edits only the isolated Rescue worktree, and leaves candidate code for the deterministic verifier.

For deterministic development, a prepared alternate proof can replace Bob:

```bash
roadmap-canary check \
  --repo /path/to/target-repo \
  --canary /path/to/.roadmap-canary/issue-1 \
  --base <base-ref> \
  --pr <pr-ref> \
  --rescue-patch /path/to/alternate-proof.patch \
  --output-dir ./run-evidence
```

Add `--json` to check commands for machine-readable output.

### 4. Promote a successful replacement witness

A successful Rescue does **not** automatically mutate the trusted Canary. After human review, explicitly promote it:

```bash
roadmap-canary promote \
  --repo /path/to/target-repo \
  --canary /path/to/.roadmap-canary/issue-1 \
  --run-dir ./run-evidence
```

Promotion replays the persisted replacement patch from scratch against the PR state before updating the stored witness and metadata.

## IBM Bob integration

The hackathon integration has been experimentally verified with Bob Shell `2.0.5` using:

- API-key authentication
- non-interactive `bob run`
- explicit isolated `--workspace`
- `agent` mode
- JSON output
- bounded `--max-turns`
- bounded `--max-cost`
- wall-clock timeout in Roadmap Canary
- MCP disabled by default
- subagents disabled by default
- direct file modification inside a temporary Git repository

Bob task ID, cost, duration, tool-call count, and final message are retained as Rescue metadata when available. See `docs/bob-integration.md` for the verified integration behavior and the handling required for agent-created untracked files.

## Proof Fidelity

Roadmap Canary does not ask an LLM to score whether a proof "looks realistic." Proof Fidelity is expressed as deterministic, human-approved evidence in the Future Contract. For the MVP this includes real integration/contract tests, protected tests that cannot be weakened, proof budgets, and verification commands that exercise the required production path.

For example, a multi-provider witness should not pass merely because a second class implements an interface. The approved evidence should require that the second provider satisfies the shared provider contract and executes through the real checkout path.

See `docs/future-contract.md` for the trust boundary and evidence model.

## Result semantics

- `SAFE`: the known executable path still verifies on the PR.
- `PATH_CHANGED`: the known path disappeared, but Rescue produced another deterministically verified path. User-facing wording: **PATH CHANGED - SAFE**.
- `ROADMAP_RISK`: the known path disappeared and no Rescue candidate passed deterministic verification within the bounded attempt.
- `STALE`: the Canary should not be attributed to the PR, for example because the witness already fails on BASE or the Future Contract has expired.

A `ROADMAP_RISK` result does **not** claim that the future capability is impossible. It means its previously demonstrated viability is no longer established by the configured bounded Rescue process.

## Current demo dependency

The engine is ready to consume the prepared demo repository once its witness and scenario refs are available. The intended demo refs are:

```text
canary/multi-provider-witness
demo/path-changed-safe
demo/roadmap-risk
```

No demo-specific logic is hard-coded into the engine.

## Design specification

The working design specification is kept temporarily under `docs/design/`. It can be removed once the implementation and final project documentation fully supersede it.
