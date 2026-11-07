"""Stage tool: close a run, guarded by the completeness check.

This is the anti-omission gate: if any (viewpoint x target) cell is
still pending, the close is REFUSED and the pending cells are listed.
A run with undigested cells can never be reported as complete.

Usage: python -m tools.close_run RUN_ID
"""

from __future__ import annotations

import argparse

try:
    from tools import common
except ImportError:  # running as a plain script file
    import common  # type: ignore

    common.bootstrap()
    from tools import common


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    common.add_common_args(parser)
    args = parser.parse_args(argv)

    store = common.RunStore(args.state_dir)
    try:
        run = store.load(args.run_id)
    except common.HarnessError as exc:
        return common.fail(str(exc))
    pending = common.pending_cells(run)
    if pending:
        common.emit(
            {
                "ok": False,
                "error": "run has undigested cells; refusing to close",
                "pending_cells": [
                    {"viewpoint": c["viewpoint"], "target": c["target"]}
                    for c in pending
                ],
            }
        )
        return 1
    run["status"] = "closed"
    run["closed_at"] = common.utcnow()
    store.save(run)
    summary = common.summarize(run)
    summary["ok"] = True
    common.emit(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
