# Future Contract and Proof Fidelity

A Roadmap Canary is meaningful only if the future capability and its acceptable evidence are defined before a PR is evaluated. The Future Contract is therefore a human-approved trust boundary, not a free-form prompt generated and judged by the same agent.

## Human responsibility

A human decides which roadmap item is stable and important enough to protect. The approved contract defines:

- the future capability that matters,
- what an executable proof must demonstrate,
- what a proof is forbidden from doing,
- which tests must not be weakened,
- which deterministic commands constitute evidence,
- the maximum size of a disposable proof,
- lifecycle metadata such as commitment and expiry.

Bob may help draft a Future Contract later, but the trusted contract used by Roadmap Canary is the approved artifact on disk.

## Minimum Viable Proof

The witness is not production implementation and is not a promise that the future feature will use that design. It is the smallest disposable executable construction that demonstrates at least one currently viable path satisfying the contract.

The witness can be replaced after architecture evolves. That is why Rescue exists: Roadmap Canary protects the capability, not a speculative architecture.

## Proof Fidelity

Proof Fidelity answers a specific question:

> Does this witness demonstrate the intended capability through meaningful production architecture, rather than satisfying a weak test with fake or isolated code?

Roadmap Canary does not calculate an AI fidelity score. Fidelity is encoded as independent deterministic evidence.

For the hackathon MVP, the evidence model uses:

1. **Verification commands** that run approved tests, type checks, builds, or architecture checks.
2. **Protected tests** whose contents are hashed before speculative work and must remain unchanged.
3. **Proof budgets** that constrain changed files, added lines, and new dependencies.
4. **Future-specific contract/integration tests** included in the approved verification commands.
5. **Real-path requirements** expressed in the Future Contract and backed by those executable tests.

A proof is accepted only when every configured deterministic check passes.

## Example: multiple payment providers

A weak witness would merely add a second class named `CanaryPayProvider` that implements an interface but is never exercised by the application.

A credible witness must instead provide executable evidence for the approved future capability. The demo contract requires that:

- at least two interchangeable providers satisfy the shared provider contract,
- the synthetic second provider executes through the real `CheckoutService -> PaymentService` path,
- existing Stripe behavior still passes,
- checkout and refund logic remain provider-agnostic,
- approved acceptance tests are not weakened,
- the proof remains within its configured change budget.

The synthetic provider itself does not need to call a real payment API. What matters is that the disposable proof exercises the real production architecture required by the contract.

## Capture boundary

`roadmap-canary capture` converts a separate witness Git ref into the trusted Canary artifact only after replaying the derived patch on a clean BASE worktree and running deterministic verification.

Conceptually:

```text
human-approved contract
        +
witness branch/ref
        |
        v
derive patch from BASE
        |
        v
clean BASE worktree
        |
        v
deterministic verification
     /           \
   PASS          FAIL
    |             |
 store Canary   reject capture
```

This prevents an unverified branch from becoming the persistent witness merely because it exists.

## Rescue boundary

When the stored witness fails on a PR, Bob is allowed to search for another proof under bounded resources. Bob's code is only a candidate.

```text
old witness fails on PR
        |
        v
bounded Bob Rescue
        |
        v
candidate workspace changes
        |
        v
same deterministic verifier
     /           \
   PASS          FAIL
    |             |
PATH CHANGED   ROADMAP RISK
  - SAFE
```

`ROADMAP_RISK` means that replacement viability was not demonstrated within the configured Rescue attempt. It does not mean that the future capability is impossible.

## Promotion boundary

A verified Rescue does not automatically rewrite the trusted Canary. Roadmap Canary first persists the result and replacement patch as evidence. After review, a human explicitly runs `roadmap-canary promote`.

Promotion replays the persisted replacement patch from scratch against the PR state. Only if it still passes the Future Contract does Roadmap Canary replace `witness.patch` and update the baseline metadata.

This creates a clear chain of trust:

```text
human-approved Future Contract
        |
verified initial witness
        |
BASE / PR replay
        |
bounded Bob proposal
        |
deterministic verification
        |
human-triggered promotion
        |
verified replacement witness
```

## Lifecycle

Roadmap items should not become permanent architectural obligations by accident. The contract may carry an expiry date. An expired contract is reported as `STALE` and must be reviewed or renewed before Roadmap Canary attributes a roadmap regression to a PR.

This keeps the mechanism aligned with committed, architecture-sensitive future work rather than speculative wishlist items.
