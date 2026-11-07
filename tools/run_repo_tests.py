"""Standalone tool: run a repository's pytest suite and report counts.

Runs the test command in the target repository, parses the pytest
summary line, and prints a JSON result to stdout. This tool is
deliberately self-contained: it imports nothing from the other harness
tools and communicates only through its arguments and its JSON output.

Usage:
    python -m tools.run_repo_tests TARGET [--cmd "python3 -m pytest -q"]
                                          [--out result.json]

Output JSON fields:
    target, command, total, passed, failed, errors, skipped,
    duration_sec, ok, failed_tests (at most 20), error (null normally)

``ok`` is true only when at least one test ran and every test passed.
Abnormal cases (no tests collected, no summary line, the command could
not be started, a timeout) still produce JSON with ``ok`` false and a
reason in ``error``; this tool does not raise. The exit code mirrors
``ok``: 0 when true, 1 when false.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_COMMAND = "python3 -m pytest -q"
MAX_FAILED_TESTS = 20
TIMEOUT_SEC = 1800

_COUNT_PATTERNS = {
    "passed": re.compile(r"(\d+) passed"),
    "failed": re.compile(r"(\d+) failed"),
    "errors": re.compile(r"(\d+) errors?"),
    "skipped": re.compile(r"(\d+) skipped"),
}
_DURATION_RE = re.compile(r"in ([\d.]+)s")
# Short-summary lines look like:
#   FAILED tests/test_x.py::test_y - AssertionError: ...
#   ERROR tests/test_x.py::test_z - ...
_FAILED_LINE_RE = re.compile(r"^(?:FAILED|ERROR) (\S+)")


def _find_summary_line(output: str) -> str | None:
    """Return the last line that looks like a pytest summary line."""
    summary = None
    for line in output.splitlines():
        if "no tests ran" in line or any(
            pattern.search(line) for pattern in _COUNT_PATTERNS.values()
        ):
            if " in " in line and line.strip().strip("=").strip():
                summary = line
    return summary


def parse_pytest_output(output: str) -> dict[str, Any]:
    """Parse pytest output text into counts and failed test names.

    Pure function of the output text so it can be unit-tested with
    fixture strings. ``duration_sec`` is None when the summary line
    carries no duration. ``error`` explains abnormal shapes (no summary
    line, zero tests); it is None for ordinary pass/fail results.
    """
    failed_tests: list[str] = []
    for line in output.splitlines():
        match = _FAILED_LINE_RE.match(line.strip())
        if match and match.group(1) not in failed_tests:
            failed_tests.append(match.group(1))

    summary = _find_summary_line(output)
    result: dict[str, Any] = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "duration_sec": None,
        "failed_tests": failed_tests[:MAX_FAILED_TESTS],
        "error": None,
    }
    if summary is None:
        result["error"] = "no pytest summary line found in output"
        return result
    for key, pattern in _COUNT_PATTERNS.items():
        match = pattern.search(summary)
        if match:
            result[key] = int(match.group(1))
    duration = _DURATION_RE.search(summary)
    if duration:
        result["duration_sec"] = float(duration.group(1))
    result["total"] = (
        result["passed"] + result["failed"] + result["errors"] + result["skipped"]
    )
    if "no tests ran" in output or result["total"] == 0:
        result["error"] = "no tests ran (0 tests collected)"
    return result


def is_ok(parsed: dict[str, Any]) -> bool:
    """All-pass judgement: something ran, nothing failed or errored."""
    return (
        parsed["error"] is None
        and parsed["total"] > 0
        and parsed["failed"] == 0
        and parsed["errors"] == 0
    )


def run_tests(target: Path, command: str) -> dict[str, Any]:
    """Run the test command in *target* and build the result dict."""
    result: dict[str, Any] = {
        "target": str(target),
        "command": command,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "duration_sec": 0.0,
        "ok": False,
        "failed_tests": [],
        "error": None,
    }
    if not target.is_dir():
        result["error"] = f"target is not a directory: {target}"
        return result
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        result["error"] = f"could not parse command: {exc}"
        return result
    if not argv:
        result["error"] = "empty test command"
        return result
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=target,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
        )
    except FileNotFoundError:
        result["error"] = f"command not found: {argv[0]}"
        result["duration_sec"] = round(time.monotonic() - started, 3)
        return result
    except subprocess.TimeoutExpired:
        result["error"] = f"test command timed out after {TIMEOUT_SEC}s"
        result["duration_sec"] = round(time.monotonic() - started, 3)
        return result
    except OSError as exc:
        result["error"] = f"could not run test command: {exc}"
        result["duration_sec"] = round(time.monotonic() - started, 3)
        return result
    elapsed = time.monotonic() - started
    parsed = parse_pytest_output((proc.stdout or "") + (proc.stderr or ""))
    result.update(
        total=parsed["total"],
        passed=parsed["passed"],
        failed=parsed["failed"],
        errors=parsed["errors"],
        skipped=parsed["skipped"],
        failed_tests=parsed["failed_tests"],
        error=parsed["error"],
    )
    if parsed["duration_sec"] is not None:
        result["duration_sec"] = parsed["duration_sec"]
    else:
        result["duration_sec"] = round(elapsed, 3)
    if result["error"] is None and proc.returncode != 0 and result["total"] == 0:
        result["error"] = f"test command exited with code {proc.returncode}"
    result["ok"] = is_ok(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="target repository path")
    parser.add_argument(
        "--cmd",
        default=DEFAULT_COMMAND,
        help=f"test command (default: {DEFAULT_COMMAND})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="also write the JSON result to this file",
    )
    args = parser.parse_args(argv)
    result = run_tests(args.target.expanduser().resolve(), args.cmd)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
