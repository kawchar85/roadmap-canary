from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .artifacts import load_canary_artifact
from .evaluation import check_canary, check_known_path
from .rescue import BobRescueAgent
from .runs import persist_run


class InspectRequest(BaseModel):
    repo: str


class LoadResultRequest(BaseModel):
    repo: str
    result_path: str


class RunRequest(BaseModel):
    repo: str
    canary: str
    base: str = "main"
    pr: str
    output_dir: str | None = None
    bob_max_turns: int = Field(default=30, ge=1, le=100)
    bob_max_cost: float = Field(default=1.50, gt=0, le=100)
    bob_timeout: int = Field(default=900, ge=1, le=7200)


_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_REPOSITORY_SLUG = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise ValueError(process.stderr.strip() or process.stdout.strip())
    return process.stdout.strip()


def _repo_cache_root() -> Path:
    configured = os.environ.get("ROADMAP_CANARY_REPO_CACHE")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".roadmap-canary" / "repos").resolve()


def _repository_slug(value: str) -> str | None:
    candidate = value.strip()
    if candidate.endswith(".git"):
        candidate = candidate[:-4]
    if not _REPOSITORY_SLUG.fullmatch(candidate):
        return None
    owner, name = candidate.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."}:
        return None
    return candidate


def _clone_or_fetch(slug: str) -> Path:
    owner, name = slug.split("/", 1)
    destination = _repo_cache_root() / owner / name
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.is_dir():
        _git(destination, "rev-parse", "--git-dir")
        process = subprocess.run(
            ["git", "-C", str(destination), "fetch", "--prune", "origin"],
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            raise ValueError(process.stderr.strip() or process.stdout.strip())
        # This checkout is Roadmap Canary-managed cache, not the user's working tree.
        # Keep it aligned with the remote default branch so newly committed Canary
        # artifacts are visible immediately after Sync repository.
        _git(destination, "reset", "--hard", "origin/HEAD")
        return destination.resolve()

    process = subprocess.run(
        ["git", "clone", f"git@github.com:{slug}.git", str(destination)],
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise ValueError(process.stderr.strip() or process.stdout.strip())
    return destination.resolve()


def _prepare_repo(value: str) -> tuple[Path, str, str]:
    raw = value.strip()
    if not raw:
        raise ValueError("Enter a repository as owner/name or a local path")

    slug = _repository_slug(raw)
    if slug is not None:
        return _clone_or_fetch(slug), slug, "github"

    repo = Path(raw).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError(f"Repository directory does not exist: {repo}")
    _git(repo, "rev-parse", "--git-dir")
    return repo, repo.name, "local"


def _resolve_repo(value: str) -> Path:
    repo = Path(value).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError(f"Repository directory does not exist: {repo}")
    _git(repo, "rev-parse", "--git-dir")
    return repo


def _resolve_inside_repo(repo: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = repo / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(repo):
        raise ValueError("Path must be inside the selected repository")
    return candidate


def _bob_status() -> dict[str, Any]:
    binary = shutil.which("bob")
    version: str | None = None
    if binary:
        process = subprocess.run(
            [binary, "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        version = (process.stdout or process.stderr).strip() or None
    return {
        "installed": binary is not None,
        "binary": binary,
        "version": version,
        "api_key_configured": bool(os.environ.get("BOB_API_KEY")),
        "ready": binary is not None and bool(os.environ.get("BOB_API_KEY")),
    }


def _canary_summary(path: Path) -> dict[str, Any] | None:
    try:
        artifact = load_canary_artifact(path)
    except Exception:
        return None
    contract = artifact.contract
    return {
        "path": str(path),
        "id": contract.id,
        "feature": contract.feature,
        "target": contract.commitment.target,
        "blocking_policy": contract.commitment.blocking_policy,
        "proof_budget": contract.proof_budget.model_dump(mode="json"),
        "must_prove": contract.must_prove,
        "must_not": contract.must_not,
        "protected_tests": contract.protected_tests,
    }


def _discover_canaries(repo: Path) -> list[dict[str, Any]]:
    root = repo / ".roadmap-canary"
    if not root.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for contract_path in sorted(root.glob("*/contract.yaml")):
        artifact_dir = contract_path.parent
        if not (artifact_dir / "witness.patch").is_file():
            continue
        summary = _canary_summary(artifact_dir)
        if summary is not None:
            found.append(summary)
    return found


def _discover_saved_runs(repo: Path) -> list[dict[str, Any]]:
    root = repo / ".roadmap-canary" / "runs"
    if not root.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for result_path in sorted(root.glob("*/result.json"), reverse=True):
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        known = data.get("known_path", {})
        runs.append(
            {
                "path": str(result_path),
                "name": result_path.parent.name,
                "status": data.get("status"),
                "feature": known.get("feature"),
                "pr_ref": known.get("pr_ref"),
                "created_at": datetime.fromtimestamp(
                    result_path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    return runs[:20]


def _refs(repo: Path) -> list[str]:
    output = _git(
        repo,
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/heads",
        "refs/remotes/origin",
    )
    refs = [line for line in output.splitlines() if line and not line.endswith("/HEAD")]
    return sorted(dict.fromkeys(refs))


def _display_ref(ref: str | None) -> str | None:
    if ref is None:
        return None
    return ref.removeprefix("origin/")


def _steps() -> list[dict[str, str]]:
    return [
        {"key": "base", "label": "BASE witness", "status": "running"},
        {"key": "pr", "label": "PR witness", "status": "running"},
        {"key": "rescue", "label": "IBM Bob Rescue", "status": "waiting"},
        {"key": "verify", "label": "Deterministic verification", "status": "waiting"},
    ]


def _update_job(job_id: str, **updates: Any) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(updates)


def _update_step(job_id: str, key: str, status: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        for step in job["steps"]:
            if step["key"] == key:
                step["status"] = status
                break


def _safe_run_name(pr_ref: str) -> str:
    safe = "".join(character if character.isalnum() else "-" for character in pr_ref)
    safe = "-".join(part for part in safe.split("-") if part)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"ui-{safe[:40] or 'run'}-{stamp}"


def _result_summary(data: dict[str, Any]) -> dict[str, Any]:
    known = data.get("known_path", {})
    rescue = data.get("rescue") or {}
    verification = rescue.get("verification") or {}
    budget = verification.get("budget") or {}
    stats = budget.get("stats") or {}
    commands = verification.get("commands") or []
    status = data.get("status")
    return {
        "status": status,
        "status_label": "PATH CHANGED - SAFE" if status == "PATH_CHANGED" else status,
        "reason": data.get("reason"),
        "canary_id": known.get("canary_id"),
        "feature": known.get("feature"),
        "base_ref": known.get("base_ref"),
        "pr_ref": known.get("pr_ref"),
        "base_display_ref": _display_ref(known.get("base_ref")),
        "pr_display_ref": _display_ref(known.get("pr_ref")),
        "base_passed": (known.get("base") or {}).get("verification_passed")
        and (known.get("base") or {}).get("patch_applied"),
        "pr_passed": (known.get("pr") or {}).get("verification_passed")
        and (known.get("pr") or {}).get("patch_applied"),
        "rescue": {
            "attempted": rescue.get("attempted", False),
            "candidate_produced": rescue.get("candidate_produced", False),
            "passed": bool(
                rescue.get("candidate_produced")
                and verification
                and verification.get("verification_passed")
                and verification.get("protected_tests_unchanged", True)
                and budget.get("passed", True)
            ),
            "agent": rescue.get("agent"),
            "cost": rescue.get("cost"),
            "task_id": rescue.get("task_id"),
            "tool_calls": rescue.get("tool_calls"),
            "last_message": rescue.get("last_message"),
            "errors": rescue.get("errors", []),
            "candidate_patch": rescue.get("candidate_patch"),
        },
        "verification": {
            "passed": verification.get("verification_passed"),
            "protected_tests_unchanged": verification.get("protected_tests_unchanged"),
            "changed_protected_tests": verification.get("changed_protected_tests", []),
            "commands": [
                {
                    "command": item.get("command"),
                    "exit_code": item.get("exit_code"),
                    "passed": item.get("exit_code") == 0,
                }
                for item in commands
            ],
            "budget_passed": budget.get("passed"),
            "budget": stats,
            "budget_violations": budget.get("violations", []),
            "errors": verification.get("errors", []),
        },
    }


def _execute_run(job_id: str, request: RunRequest) -> None:
    try:
        repo = _resolve_repo(request.repo)
        canary = _resolve_inside_repo(repo, request.canary)
        if not canary.is_dir():
            raise ValueError(f"Canary artifact does not exist: {canary}")

        _update_job(job_id, phase="Replaying the stored witness on BASE and PR")
        known = check_known_path(
            repo,
            canary,
            base_ref=request.base,
            pr_ref=request.pr,
        )
        _update_step(job_id, "base", "pass" if known.base.passed else "fail")
        _update_step(job_id, "pr", "pass" if known.pr.passed else "fail")

        if known.rescue_required:
            _update_step(job_id, "rescue", "running")
            _update_job(job_id, phase="IBM Bob is searching for a replacement path")
        else:
            _update_step(job_id, "rescue", "skipped")

        result = check_canary(
            repo,
            canary,
            base_ref=request.base,
            pr_ref=request.pr,
            rescue_agent=BobRescueAgent(
                max_turns=request.bob_max_turns,
                max_cost=request.bob_max_cost,
                timeout_seconds=request.bob_timeout,
            ),
            known_path=known,
        )

        if result.rescue is None:
            _update_step(job_id, "verify", "skipped")
        else:
            if result.rescue.candidate_produced:
                _update_step(job_id, "rescue", "pass")
            else:
                _update_step(job_id, "rescue", "fail")
            if result.rescue.verification is None:
                _update_step(job_id, "verify", "skipped")
            else:
                _update_step(
                    job_id,
                    "verify",
                    "pass" if result.rescue.verification.passed else "fail",
                )

        if request.output_dir:
            output_dir = _resolve_inside_repo(repo, request.output_dir)
        else:
            output_dir = repo / ".roadmap-canary" / "runs" / _safe_run_name(request.pr)
        persist_run(result, output_dir)

        raw = json.loads(result.model_dump_json())
        _update_job(
            job_id,
            status="completed",
            phase="Analysis complete",
            result=raw,
            summary=_result_summary(raw),
            evidence_dir=str(output_dir),
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="error",
            phase="Analysis failed",
            error=str(exc),
        )


def create_app() -> FastAPI:
    app = FastAPI(
        title="Roadmap Canary",
        description="Local-first UI for executable future-viability checks.",
        version="0.1.0",
    )

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        index_path = Path(__file__).with_name("static") / "index.html"
        html = index_path.read_text(encoding="utf-8")
        collapse_advanced = """
<script>
  window.addEventListener("pageshow", () => {
    document.querySelectorAll("details.advanced").forEach((details) => {
      details.open = false;
    });
  });
</script>
"""
        return HTMLResponse(html.replace("</body>", collapse_advanced + "</body>"))

    @app.get("/api/system")
    def system_status() -> dict[str, Any]:
        return {"bob": _bob_status()}

    @app.post("/api/inspect")
    def inspect_repo(request: InspectRequest) -> dict[str, Any]:
        try:
            repo, display_name, source = _prepare_repo(request.repo)
            current_branch = _git(repo, "branch", "--show-current") or "detached"
            return {
                "repo": display_name,
                "local_path": str(repo),
                "source": source,
                "current_branch": current_branch,
                "refs": _refs(repo),
                "canaries": _discover_canaries(repo),
                "saved_runs": _discover_saved_runs(repo),
                "synced_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/runs")
    def start_run(request: RunRequest) -> dict[str, str]:
        try:
            repo = _resolve_repo(request.repo)
            canary = _resolve_inside_repo(repo, request.canary)
            if not canary.is_dir():
                raise ValueError(f"Canary artifact does not exist: {canary}")
            _git(repo, "rev-parse", f"{request.base}^{{commit}}")
            _git(repo, "rev-parse", f"{request.pr}^{{commit}}")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        job_id = uuid4().hex
        with _jobs_lock:
            _jobs[job_id] = {
                "id": job_id,
                "status": "running",
                "phase": "Preparing isolated worktrees",
                "steps": _steps(),
                "limits": {
                    "max_turns": request.bob_max_turns,
                    "max_cost": request.bob_max_cost,
                    "timeout": request.bob_timeout,
                },
                "result": None,
                "summary": None,
                "evidence_dir": None,
                "error": None,
            }
        thread = threading.Thread(
            target=_execute_run,
            args=(job_id, request),
            name=f"roadmap-canary-ui-{job_id[:8]}",
            daemon=True,
        )
        thread.start()
        return {"job_id": job_id}

    @app.get("/api/runs/{job_id}")
    def get_run(job_id: str) -> dict[str, Any]:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Run not found")
            return json.loads(json.dumps(job))

    @app.post("/api/load-result")
    def load_result(request: LoadResultRequest) -> dict[str, Any]:
        try:
            repo = _resolve_repo(request.repo)
            result_path = _resolve_inside_repo(repo, request.result_path)
            data = json.loads(result_path.read_text(encoding="utf-8"))
            return {
                "result": data,
                "summary": _result_summary(data),
                "evidence_dir": str(result_path.parent),
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_app()
