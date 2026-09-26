# Roadmap Canary UI

Roadmap Canary includes a local-first web interface for human review while keeping the CLI as the automation and CI surface.

The UI calls the same Python engine used by the CLI. IBM Bob is still only the proposal mechanism: final `SAFE`, `PATH_CHANGED`, `ROADMAP_RISK`, and `STALE` statuses come from executable evidence and deterministic verification.

## Start

Install the project in the active virtual environment:

```bash
pip install -e '.[dev]'
```

Export the IBM Bob API key in the same shell that launches the UI:

```bash
export BOB_API_KEY='...'
```

Then start the local interface:

```bash
roadmap-canary ui
```

The default address is `http://127.0.0.1:8765` and the browser opens automatically. Use `--no-open` to suppress that behavior.

## Demo workflow

1. Confirm that Bob Shell is detected and `BOB_API_KEY` is configured.
2. Enter the local path to the product repository, for example `/Users/.../roadmap-canary-demo`.
3. Click **Inspect repository**. The UI discovers captured Canary artifacts under `.roadmap-canary/` and available local/remote refs.
4. Select the Future Capability, BASE ref, and incoming PR/branch ref.
5. Keep the final-demo Bob limits consistent across scenarios. The current demo configuration is 30 turns, 1.50 Bobcoins, and a 900-second timeout.
6. Click **Analyze roadmap impact**.
7. The UI renders the BASE witness result, PR witness result, IBM Bob Rescue state, deterministic verification, proof budget, and final verdict.
8. Every completed run is persisted below `.roadmap-canary/runs/`. Saved runs can be reopened from the UI without spending Bobcoins.

## Presentation mode

For the hackathon presentation, run each final scenario once after code and refs are frozen, then preserve the generated evidence. During a live presentation, **Saved evidence** can reopen those genuine runs instantly. This avoids depending on agent latency or network variability while still showing results produced by real IBM Bob runs.

The intended visual contrast is:

```text
Scenario A
BASE witness        PASS
PR witness          FAIL
IBM Bob Rescue      PASS
Deterministic proof PASS
PATH CHANGED - SAFE

Scenario B
BASE witness        PASS
PR witness          FAIL
IBM Bob candidate   FUNCTIONALLY PASSES
Proof budget        FAIL (for example, 5 files > 3)
ROADMAP RISK
```

`ROADMAP_RISK` never means the future capability is impossible. It means replacement viability was not demonstrated within the human-approved bounded Rescue contract.

## Security and scope

- The server binds to `127.0.0.1` by default.
- The API key is read from the server process environment and is never returned to the browser.
- Repository, Canary, output, and saved-result paths are constrained to the selected local repository.
- Replay and Rescue continue to use isolated Git worktrees; the active working tree is not modified.
- The UI intentionally does not include accounts, databases, analytics, contract authoring, or GitHub App installation. Those are outside the hackathon MVP.
