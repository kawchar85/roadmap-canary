# Roadmap Canary UI

Roadmap Canary includes a compact local-first web interface for reviewing roadmap impact while keeping the CLI as the automation and CI surface.

The UI uses the same Python engine as the CLI. IBM Bob may propose a replacement proof during Rescue, but final `SAFE`, `PATH_CHANGED`, `ROADMAP_RISK`, and `STALE` statuses come from executable evidence and deterministic verification.

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

## Repository workflow

The primary repository input is a GitHub repository slug:

```text
kawchar85/roadmap-canary-demo
```

Roadmap Canary stores GitHub-backed repositories under:

```text
~/.roadmap-canary/repos/<owner>/<repository>/
```

On first use it clones with SSH. On later inspections it runs `git fetch --prune origin` rather than mutating the checked-out branch with `git pull`.

A local repository can still be selected through **Use local repository**.

## Main workflow

1. Connect or sync the repository.
2. Select a captured Future Capability / Canary.
3. Review its compact Future Contract summary and proof budget if needed.
4. Select the incoming branch or PR ref and BASE ref.
5. Keep the final-demo Bob limits consistent across scenarios: 30 turns, 1.50 Bobcoins, and a 900-second timeout.
6. Click **Analyze roadmap impact**.
7. Review the execution sequence: BASE witness, PR witness, IBM Bob Rescue, and deterministic verification.
8. Review the final verdict and concrete verification evidence.

The working screen intentionally avoids product-marketing elements. Implementation concepts such as isolated worktrees or bounded Rescue remain documented in the README and engineering documentation instead of appearing as decorative UI.

## Future Contract drawer

The selected capability shows only the information needed during normal use:

- commitment / advisory policy,
- proof budget,
- link to **View Future Contract**.

The drawer exposes:

- `must_prove`,
- `must_not`,
- protected tests,
- proof-budget limits.

## Result view

The result screen is evidence-first. A typical roadmap-risk result looks like:

```text
BASE witness                         Passed
PR witness                           Failed
IBM Bob Rescue                       Candidate found
Deterministic verification           Failed

ROADMAP RISK

Existing tests                       Passed
Typecheck                            Passed
Future capability tests              Passed
Protected tests                      Unchanged

Files changed                        5 / 3
Added lines                          51 / 120
New dependencies                     0 / 0
```

When a Rescue candidate exists, **View candidate diff** exposes the exact patch that Roadmap Canary verified or rejected.

## Recent runs

Completed runs are persisted below `.roadmap-canary/runs/` in the selected repository. The UI lists them under **Recent runs** and can reopen the saved `result.json` without spending Bobcoins or depending on agent latency.

This is the recommended live-presentation path after the final scenarios have been run once and their evidence has been preserved.

## IBM Bob status

IBM Bob appears as a small integration indicator in the application header instead of a permanent setup card. Clicking it shows:

- Shell detection,
- installed version,
- API-key availability.

Bob is required only when Rescue is needed.

## Security and scope

- The server binds to `127.0.0.1` by default.
- The Bob API key is read from the server process environment and is never returned to the browser.
- GitHub repositories are cloned through the user's existing SSH configuration.
- Repository, Canary, output, and saved-result paths remain constrained to the selected local repository copy.
- Replay and Rescue continue to use isolated Git worktrees; the active working tree is not modified by those operations.
- The UI intentionally does not include accounts, databases, analytics dashboards, contract authoring, or GitHub App installation. Those remain outside the hackathon MVP.
