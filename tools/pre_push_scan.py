"""Standalone tool: scan tracked files for leaked secrets / personal data.

Walks the files tracked by git (``git ls-files``) in the target
repository and reports where generic leak patterns occur. Only the
location and the pattern *kind* are reported -- the matched string
itself is never printed, stored, or included in the output.

Generic pattern kinds:
    email               an email address
    ipv4                an IPv4 address
    token_prefix        a token starting ghp_ / github_pat_ / sk- / AKIA
    private_key_header  a "BEGIN ... PRIVATE KEY" header
    local_literal       a literal from the local patterns file

Local patterns: when a ``scan-patterns.local.json`` file exists in the
target repository root or in this harness's repository root, its
``{"literals": [...]}`` entries are scanned for as plain substrings and
reported as kind ``local_literal``. The file is git-ignored and is
never created by this tool. ``--patterns PATH`` adds one explicitly.

Excluded from the scan: anything under ``.venv/`` or ``state/``, binary
files, and the local patterns file itself.

Usage:
    python -m tools.pre_push_scan TARGET [--patterns PATH]
                                         [--out result.json]

Output JSON: ``ok`` (true when there are no hits), ``hits`` (a list of
{file, line, kind}), plus ``target``, ``files_scanned`` and ``error``.
The exit code mirrors ``ok``: 0 when clean, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

LOCAL_PATTERNS_NAME = "scan-patterns.local.json"

# Generic patterns: (kind, compiled regex). Kept deliberately broad and
# free of any personal value; personal literals belong in the local
# patterns file, which is never committed.
GENERIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("ipv4", re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")),
    (
        "token_prefix",
        re.compile(
            r"(?:ghp_[A-Za-z0-9]{20,}"
            r"|github_pat_[A-Za-z0-9_]{20,}"
            r"|sk-[A-Za-z0-9_-]{16,}"
            r"|AKIA[A-Z0-9]{16})"
        ),
    ),
    (
        "private_key_header",
        re.compile(r"BEGIN [A-Z0-9 ]*PRIVATE KEY"),
    ),
]

EXCLUDED_DIR_PARTS = {".venv"}
EXCLUDED_TOP_DIRS = {"state"}


def is_excluded(relative_path: str) -> bool:
    """True for paths the scan must skip (.venv, state/, patterns file)."""
    parts = Path(relative_path).parts
    if not parts:
        return True
    if parts[0] in EXCLUDED_TOP_DIRS:
        return True
    if any(part in EXCLUDED_DIR_PARTS for part in parts):
        return True
    if parts[-1] == LOCAL_PATTERNS_NAME:
        return True
    return False


def is_binary(data: bytes) -> bool:
    """Binary heuristic: a NUL byte in the first chunk of content."""
    return b"\x00" in data[:8192]


def load_local_literals(path: Path) -> list[str]:
    """Load literal strings from a local patterns file.

    Returns an empty list when the file is missing or malformed; the
    scan then proceeds with the generic patterns only.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    literals = raw.get("literals", []) if isinstance(raw, dict) else []
    return [str(item) for item in literals if str(item)]


def scan_text(text: str, literals: list[str]) -> list[dict[str, Any]]:
    """Scan one file's text; return hits as {line, kind} (no content).

    At most one hit per (line, kind) pair, so counts line up with a
    line-based manual grep for the same patterns.
    """
    hits: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        seen_kinds: set[str] = set()
        for kind, pattern in GENERIC_PATTERNS:
            if kind not in seen_kinds and pattern.search(line):
                hits.append({"line": lineno, "kind": kind})
                seen_kinds.add(kind)
        if literals and "local_literal" not in seen_kinds:
            if any(literal in line for literal in literals):
                hits.append({"line": lineno, "kind": "local_literal"})
    return hits


def list_tracked_files(target: Path) -> list[str]:
    """Return the repository's tracked files via ``git ls-files``."""
    proc = subprocess.run(
        ["git", "-C", str(target), "ls-files"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        stderr_lines = (proc.stderr or "").strip().splitlines()
        detail = stderr_lines[-1] if stderr_lines else "unknown git error"
        raise ScanError(f"git ls-files failed: {detail}")
    return [line for line in proc.stdout.splitlines() if line.strip()]


class ScanError(Exception):
    """A scan-level failure reported through the JSON error field."""


def collect_literals(target: Path, extra: Path | None) -> list[str]:
    """Merge literals from the default locations and --patterns."""
    candidates = [
        target / LOCAL_PATTERNS_NAME,
        Path(__file__).resolve().parent.parent / LOCAL_PATTERNS_NAME,
    ]
    if extra is not None:
        candidates.append(extra)
    literals: list[str] = []
    for candidate in candidates:
        for literal in load_local_literals(candidate):
            if literal not in literals:
                literals.append(literal)
    return literals


def scan_repo(target: Path, literals: list[str]) -> dict[str, Any]:
    """Scan *target* and build the result dict (never raises)."""
    result: dict[str, Any] = {
        "target": str(target),
        "ok": False,
        "hits": [],
        "files_scanned": 0,
        "error": None,
    }
    if not target.is_dir():
        result["error"] = f"target is not a directory: {target}"
        return result
    try:
        tracked = list_tracked_files(target)
    except ScanError as exc:
        result["error"] = str(exc)
        return result
    except OSError as exc:
        result["error"] = f"could not run git: {exc}"
        return result
    hits: list[dict[str, Any]] = []
    scanned = 0
    for relative in tracked:
        if is_excluded(relative):
            continue
        file_path = target / relative
        try:
            data = file_path.read_bytes()
        except OSError:
            continue
        if is_binary(data):
            continue
        scanned += 1
        text = data.decode("utf-8", errors="replace")
        for hit in scan_text(text, literals):
            hits.append({"file": relative, "line": hit["line"], "kind": hit["kind"]})
    result["hits"] = hits
    result["files_scanned"] = scanned
    result["ok"] = not hits
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="target repository path")
    parser.add_argument(
        "--patterns",
        type=Path,
        default=None,
        help="extra local patterns file (JSON with a 'literals' list)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="also write the JSON result to this file",
    )
    args = parser.parse_args(argv)
    target = args.target.expanduser().resolve()
    literals = collect_literals(target, args.patterns)
    result = scan_repo(target, literals)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
