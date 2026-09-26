# IBM Bob Integration

This document records behavior that has been experimentally verified for the Roadmap Canary hackathon integration.

## Verified environment

- Bob Shell version: `2.0.5`
- Bob Shell commit: `2dc180906`
- Binary path on the test machine: `/opt/homebrew/bin/bob`
- Authentication: `BOB_API_KEY` using the hackathon IBM Bob enterprise team
- Team: `ibm-hackathon-lablab`

No API key is stored in this repository.

## Verified non-interactive invocation

The following pattern works:

```bash
bob run "Reply with exactly BOB_READY"
```

Bob returned `BOB_READY` and reported task metadata including task ID, duration, cost, and tool-call count.

## Verified isolated workspace editing

The following command was tested successfully against a temporary Git repository:

```bash
bob run \
  --workspace /tmp/bob-roadmap-test \
  --mode agent \
  --format json \
  --max-turns 3 \
  "Create a file named bob-proof.txt containing exactly ROADMAP_CANARY_BOB_OK. Do not modify any other file."
```

Observed structured result shape:

```json
{
  "type": "result",
  "timestamp": "2026-09-26T08:04:01.078Z",
  "status": "success",
  "stats": {
    "task_id": "5e927ef6e5066c034acacde296bac4d2",
    "duration_ms": 5867,
    "session_costs": 0.041754,
    "max_cost": 0,
    "tool_calls": 1
  },
  "last_message": "..."
}
```

The workspace contained the requested untracked file after Bob exited.

## Important Git behavior

Plain `git diff` does not include newly created untracked files. The verified experiment showed:

```text
?? bob-proof.txt
```

while `git diff` was empty.

After intent-to-add staging:

```bash
git add -N .
git diff --binary
```

the new file appeared in the patch.

Roadmap Canary therefore normalizes all candidate changes before preserving or measuring a Rescue patch. The engine must not trust plain `git diff` immediately after an agent run.

## Integration boundary

The intended runtime path is:

```text
Roadmap Canary
    |
    v
isolated Git worktree at PR state
    |
    v
bob run --workspace <worktree> --mode agent --format json
    |
    v
Bob edits candidate code
    |
    v
Roadmap Canary captures the complete workspace diff
    |
    v
deterministic verification
    |
    +--> PATH_CHANGED when replacement proof verifies
    |
    +--> ROADMAP_RISK when no replacement proof verifies within the bounded attempt
```

Bob does not decide the final Roadmap Canary status.

## Current adapter

`BobRescueAgent`:

- builds a Rescue prompt from the human-approved Future Contract and known witness failure evidence,
- invokes Bob Shell against the isolated Rescue worktree,
- uses `agent` mode,
- requests JSON output,
- bounds the attempt by `max_turns` and a wall-clock timeout,
- parses Bob task metadata,
- checks whether Bob actually left workspace changes,
- returns only a candidate proposal to the engine.

The normal verifier then independently checks tests, protected-test integrity, proof budget, and other contract evidence.
