"""Shared core for the inventory harness tools.

The harness is a set of small, loosely coupled stage tools. The tools
never call each other; they coordinate only through two file formats:
the config file (viewpoints and target settings) and the per-run state
JSON. This module holds the shared definitions those formats rely on:
config loading, target discovery, the run store, cell bookkeeping, and
the candidate state machine.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Cell states: a cell is one (viewpoint x target) pair in a run.
CELL_PENDING = "pending"
CELL_DONE_WITH_CANDIDATES = "done_with_candidates"
CELL_DONE_NO_CANDIDATES = "done_no_candidates"

# Candidate states.
FOUND = "found"
CHARACTERIZED = "characterized"
IN_PROGRESS = "in_progress"
REVIEWED = "reviewed"
SCANNED = "scanned"
PUSHED = "pushed"
REPORTED = "reported"
DECISION_PENDING = "decision_pending"
REJECTED_AS_SPEC = "rejected_as_spec"

TERMINAL_STATES = frozenset({REPORTED, REJECTED_AS_SPEC})

# Allowed forward transitions. DECISION_PENDING may additionally resume
# to the state it came from (stored as ``pending_from`` on the
# candidate); that dynamic edge is handled in ``allowed_next_states``.
_TRANSITIONS: dict[str, set[str]] = {
    FOUND: {CHARACTERIZED, DECISION_PENDING, REJECTED_AS_SPEC},
    CHARACTERIZED: {IN_PROGRESS, DECISION_PENDING, REJECTED_AS_SPEC},
    IN_PROGRESS: {REVIEWED, DECISION_PENDING, REJECTED_AS_SPEC},
    REVIEWED: {SCANNED, DECISION_PENDING, REJECTED_AS_SPEC},
    SCANNED: {PUSHED, DECISION_PENDING, REJECTED_AS_SPEC},
    PUSHED: {REPORTED, DECISION_PENDING},
    DECISION_PENDING: {REJECTED_AS_SPEC},
    REPORTED: set(),
    REJECTED_AS_SPEC: set(),
}

ALL_STATES = frozenset(_TRANSITIONS)


class HarnessError(Exception):
    """Any misuse the tools must refuse (bad input, illegal move)."""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_run_id() -> str:
    return datetime.now().strftime("run-%Y%m%d-%H%M%S")


def harness_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_config_path() -> Path:
    return harness_root() / "config.json"


def default_state_dir() -> Path:
    return harness_root() / "state"


class Config:
    """Parsed harness config (viewpoints registry + target settings)."""

    def __init__(self, raw: dict[str, Any]) -> None:
        targets = raw.get("targets", {})
        mirrors = targets.get("mirrors_dir", "")
        self.mirrors_dir = Path(mirrors).expanduser() if mirrors else None
        self.extra_targets: list[dict[str, str]] = list(
            targets.get("extra_targets", [])
        )
        self.exclude: set[str] = set(targets.get("exclude", []))
        viewpoints = raw.get("viewpoints", [])
        ids = [v["id"] for v in viewpoints]
        if len(ids) != len(set(ids)):
            raise HarnessError("viewpoint ids must be unique in config")
        self.viewpoints: list[dict[str, Any]] = viewpoints

    def enabled_viewpoints(self) -> list[dict[str, Any]]:
        return [v for v in self.viewpoints if v.get("enabled", True)]


def load_config(path: Path) -> Config:
    if not path.is_file():
        raise HarnessError(f"config file not found: {path}")
    return Config(json.loads(path.read_text(encoding="utf-8")))


def discover_targets(config: Config) -> list[dict[str, str]]:
    """Enumerate targets: every git repo under the mirrors dir plus the
    configured extra targets, minus the exclusion list. New repos are
    picked up automatically on the next call."""
    found: dict[str, str] = {}
    if config.mirrors_dir is not None and config.mirrors_dir.is_dir():
        for child in sorted(config.mirrors_dir.iterdir()):
            if child.is_dir() and (child / ".git").exists():
                found[child.name] = str(child)
    for extra in config.extra_targets:
        found[extra["name"]] = str(Path(extra["path"]).expanduser())
    for name in config.exclude:
        found.pop(name, None)
    return [{"name": name, "path": path} for name, path in sorted(found.items())]


class RunStore:
    """Persists one JSON file per run under ``<state_dir>/runs/``."""

    def __init__(self, state_dir: Path) -> None:
        self.runs_dir = state_dir / "runs"

    def path_for(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def save(self, run: dict[str, Any]) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.runs_dir, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(run, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path_for(run["run_id"]))

    def load(self, run_id: str) -> dict[str, Any]:
        path = self.path_for(run_id)
        if not path.is_file():
            raise HarnessError(f"run not found: {run_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def latest_run_id(self) -> str:
        if not self.runs_dir.is_dir():
            raise HarnessError("no runs found")
        files = sorted(self.runs_dir.glob("*.json"))
        if not files:
            raise HarnessError("no runs found")
        return files[-1].stem


def new_run(
    run_id: str,
    viewpoints: list[dict[str, Any]],
    targets: list[dict[str, str]],
) -> dict[str, Any]:
    cells = [
        {
            "viewpoint": viewpoint["id"],
            "target": target["name"],
            "status": CELL_PENDING,
            "candidate_ids": [],
            "note": None,
            "updated_at": None,
        }
        for viewpoint in viewpoints
        for target in targets
    ]
    return {
        "run_id": run_id,
        "created_at": utcnow(),
        "status": "open",
        "viewpoints": [v["id"] for v in viewpoints],
        "targets": targets,
        "cells": cells,
        "candidates": [],
        "next_candidate_seq": 1,
    }


def find_cell(run: dict[str, Any], viewpoint: str, target: str) -> dict[str, Any]:
    for cell in run["cells"]:
        if cell["viewpoint"] == viewpoint and cell["target"] == target:
            return cell
    raise HarnessError(f"no such cell: viewpoint={viewpoint} target={target}")


def find_candidate(run: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for candidate in run["candidates"]:
        if candidate["id"] == candidate_id:
            return candidate
    raise HarnessError(f"no such candidate: {candidate_id}")


def pending_cells(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in run["cells"] if c["status"] == CELL_PENDING]


def add_candidate(
    run: dict[str, Any], viewpoint: str, target: str, title: str
) -> dict[str, Any]:
    if run["status"] == "closed":
        raise HarnessError("run is closed; cannot add candidates")
    cell = find_cell(run, viewpoint, target)
    seq = run["next_candidate_seq"]
    run["next_candidate_seq"] = seq + 1
    candidate = {
        "id": f"C-{seq:03d}",
        "viewpoint": viewpoint,
        "target": target,
        "title": title,
        "state": FOUND,
        "pending_from": None,
        "history": [{"from": None, "to": FOUND, "at": utcnow()}],
    }
    run["candidates"].append(candidate)
    if candidate["id"] not in cell["candidate_ids"]:
        cell["candidate_ids"].append(candidate["id"])
    return candidate


def mark_cell(
    run: dict[str, Any],
    viewpoint: str,
    target: str,
    result: str,
    note: str | None = None,
) -> dict[str, Any]:
    if run["status"] == "closed":
        raise HarnessError("run is closed; cannot mark cells")
    cell = find_cell(run, viewpoint, target)
    if result == "candidates":
        if not cell["candidate_ids"]:
            raise HarnessError(
                "cell has no candidates yet; register candidates first, " "then mark it"
            )
        cell["status"] = CELL_DONE_WITH_CANDIDATES
    elif result == "none":
        cell["status"] = CELL_DONE_NO_CANDIDATES
    else:
        raise HarnessError(f"unknown mark result: {result}")
    cell["note"] = note
    cell["updated_at"] = utcnow()
    return cell


def allowed_next_states(candidate: dict[str, Any]) -> set[str]:
    allowed = set(_TRANSITIONS[candidate["state"]])
    if candidate["state"] == DECISION_PENDING and candidate.get("pending_from"):
        allowed.add(candidate["pending_from"])
    return allowed


def advance_candidate(
    run: dict[str, Any], candidate_id: str, to_state: str
) -> dict[str, Any]:
    candidate = find_candidate(run, candidate_id)
    if to_state not in ALL_STATES:
        raise HarnessError(f"unknown candidate state: {to_state}")
    if to_state not in allowed_next_states(candidate):
        raise HarnessError(
            f"invalid transition: {candidate['state']} -> {to_state} "
            f"(allowed: {sorted(allowed_next_states(candidate))})"
        )
    previous = candidate["state"]
    if to_state == DECISION_PENDING:
        candidate["pending_from"] = previous
    elif previous == DECISION_PENDING:
        candidate["pending_from"] = None
    candidate["state"] = to_state
    candidate["history"].append({"from": previous, "to": to_state, "at": utcnow()})
    return candidate


def summarize(run: dict[str, Any]) -> dict[str, Any]:
    cells_by_status: dict[str, int] = {}
    for cell in run["cells"]:
        cells_by_status[cell["status"]] = cells_by_status.get(cell["status"], 0) + 1
    candidates_by_state: dict[str, int] = {}
    for candidate in run["candidates"]:
        state = candidate["state"]
        candidates_by_state[state] = candidates_by_state.get(state, 0) + 1
    return {
        "run_id": run["run_id"],
        "run_status": run["status"],
        "cells_total": len(run["cells"]),
        "cells_by_status": cells_by_status,
        "pending_cells": [
            {"viewpoint": c["viewpoint"], "target": c["target"]}
            for c in pending_cells(run)
        ],
        "candidates_total": len(run["candidates"]),
        "candidates_by_state": candidates_by_state,
    }


def add_common_args(parser: Any) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="config file (default: harness config.json)",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=default_state_dir(),
        help="state directory (default: harness state/)",
    )


def emit(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def fail(message: str) -> int:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    return 1


def run_main(func: Any) -> int:
    try:
        return func()
    except HarnessError as exc:
        return fail(str(exc))


def bootstrap() -> None:
    """Allow running a tool file directly (python tools/<tool>.py)."""
    sys.path.insert(0, str(harness_root()))
