# Roadmap Canary

**Regression testing for software you haven't built yet.**

Traditional CI tells you whether today's software still works. Roadmap Canary asks a second question:

> **Does this code change still leave a demonstrated viable path to a committed future capability?**

A refactor can keep every current test green while quietly making a planned feature much harder to build. Roadmap Canary makes that kind of regression visible.

![Roadmap Canary analysis pipeline](docs/assets/roadmap-canary-pipeline.gif)

## How it works

For each future capability the team wants to protect, Roadmap Canary keeps two things:

- a **human-approved Future Contract** defining what must remain possible, what evidence counts, protected tests/surfaces, and the allowed proof budget
- a **verified witness**, which is a small disposable executable proof that the capability is achievable from the current architecture

The witness is not the future product implementation and is not intended to be merged into production. It only establishes a known-good path that future changes can be tested against.

The central trust boundary is:

> **Bob proposes. Roadmap Canary verifies.**

IBM Bob may search for a replacement path when the known witness stops working, but Bob never decides the final result. Roadmap Canary independently checks the candidate using the approved verification commands, protected-test integrity, and proof budget.

## Establishing a future capability

A capability becomes an active Canary only after a baseline has been proven.

1. Define and approve the Future Contract.
2. Prepare a minimal witness on a separate Git ref.
3. Capture it with Roadmap Canary.
4. Roadmap Canary replays the witness on a clean BASE worktree and accepts it only if deterministic verification passes.

Example:

```bash
roadmap-canary capture \
  --repo /path/to/target-repo \
  --contract examples/issue-1/contract.yaml \
  --base main \
  --witness canary/multi-provider-witness \
  --output /path/to/target-repo/.roadmap-canary/issue-1
```

The resulting Canary artifact contains the approved contract and executable evidence:

```text
.roadmap-canary/
  issue-1/
    contract.yaml
    witness.patch
    metadata.json
    evidence.json
```

`witness.patch` is a minimal proof, not production feature code.

## Quick start

To enable IBM Bob Rescue, set an IBM Bob API key in your environment. Keep API keys out of source control.

```bash
git clone git@github.com:kawchar85/roadmap-canary.git
cd roadmap-canary

pip install -e '.[dev]'

export BOB_API_KEY="YOUR_BOB_API_KEY"

roadmap-canary ui
```

The UI accepts a repository in `owner/repo` form. Public target repositories are cloned over HTTPS. Private repositories require suitable Git credentials, or you can use **Use local repository**.

IBM Bob is invoked only when the known witness passes on BASE but no longer works on the selected change.

## Demo

Explore the verified Roadmap Canary demo in your browser:

**[Open the public demo](https://kawchar85.github.io/roadmap-canary-demo/)**

The public demo replays saved, verified analyses from the [`roadmap-canary-demo`](https://github.com/kawchar85/roadmap-canary-demo) repository, so the complete workflow can be explored without IBM Bob credentials.

```text
Repository:        kawchar85/roadmap-canary-demo
Future capability: Multiple payment providers
Base:              main
```

Two prepared changes demonstrate the two important outcomes:

### Demo A: path changed, future preserved

```text
Change: demo/path-changed-safe
```

Expected flow:

```text
BASE witness                 PASS
Change witness               KNOWN PATH BROKEN
IBM Bob Rescue               candidate produced
Deterministic verification   PASS
Result                       PATH CHANGED - SAFE
```

The original implementation path disappeared, but Bob found another small path that satisfied the same Future Contract and proof budget.

### Demo B: roadmap risk

```text
Change: demo/roadmap-risk
```

Expected flow:

```text
BASE witness                 PASS
Change witness               KNOWN PATH BROKEN
IBM Bob Rescue               candidate produced
Deterministic verification   REJECTED
Result                       ROADMAP RISK
```

The Rescue candidate can satisfy the functional checks, but exceeds the approved proof budget. This demonstrates how today's software can remain green while a committed future capability becomes materially more expensive to preserve.

To run Roadmap Canary against your own repository with live IBM Bob Rescue, follow the [Quick start](#quick-start) instructions above.

## Result semantics

- **SAFE**: the known executable path still verifies on the proposed change.
- **PATH CHANGED - SAFE**: the known path disappeared, but Rescue produced another path that passed deterministic verification.
- **ROADMAP RISK**: the known path disappeared and no Rescue candidate passed the approved deterministic verification within the bounded attempt.
- **STALE**: the Canary cannot be attributed to the proposed change, for example because the witness already fails on BASE or the Future Contract has expired.

`ROADMAP RISK` does not mean the future capability is impossible. It means the previously demonstrated low-cost path is no longer established under the approved constraints.

## Proof fidelity

Roadmap Canary does not ask an LLM whether a proof "looks realistic." Proof quality is encoded in the human-approved Future Contract through executable tests, protected surfaces, protected tests, verification commands, and explicit proof budgets.

For example, the multi-provider demo does not pass merely because a second class implements an interface. The proof must exercise the real checkout and refund paths while preserving the provider-agnostic architecture.

See `docs/future-contract.md` for the trust boundary and evidence model.

## IBM Bob integration

Roadmap Canary uses IBM Bob Shell in a bounded isolated Rescue worktree. Rescue can be constrained by turns, Bobcoin cost, and wall-clock time. Bob task metadata and the candidate patch are retained as run evidence when available.

See `docs/bob-integration.md` for the integration details.

## CLI

Replay a known witness on BASE and a proposed change:

```bash
roadmap-canary check-known-path \
  --repo /path/to/target-repo \
  --canary /path/to/target-repo/.roadmap-canary/issue-1 \
  --base main \
  --pr <change-ref>
```

Run the full flow with IBM Bob Rescue when required:

```bash
roadmap-canary check \
  --repo /path/to/target-repo \
  --canary /path/to/target-repo/.roadmap-canary/issue-1 \
  --base main \
  --pr <change-ref> \
  --bob-max-turns 30 \
  --bob-max-cost 1.50 \
  --bob-timeout 900 \
  --output-dir ./run-evidence
```

A successful Rescue does not automatically replace the trusted witness. After human review, promote it explicitly:

```bash
roadmap-canary promote \
  --repo /path/to/target-repo \
  --canary /path/to/target-repo/.roadmap-canary/issue-1 \
  --run-dir ./run-evidence
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```
