"""Stage tool: move one candidate along its lifecycle.

Legal path: found -> characterized -> in_progress -> reviewed ->
scanned -> pushed -> reported. From any non-terminal state a candidate
may detour to decision_pending (and later resume to the state it came
from) or to rejected_as_spec. Illegal jumps are refused.

Some transitions require an evidence reference, recorded in the
candidate history: reviewed needs the review result, scanned the
pre-push scan record, pushed the commit hash (7-40 hex chars), and
reported the report destination. Pass it with --evidence.

Usage: python -m tools.advance_candidate RUN_ID CANDIDATE_ID --to STATE
       [--evidence REF]
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
    parser.add_argument("candidate_id")
    parser.add_argument("--to", required=True, help="next candidate state")
    parser.add_argument(
        "--evidence",
        default=None,
        help="evidence reference (required for reviewed/scanned/pushed/reported)",
    )
    common.add_common_args(parser)
    args = parser.parse_args(argv)

    def run() -> int:
        store = common.RunStore(args.state_dir)
        run = store.load(args.run_id)
        candidate = common.advance_candidate(
            run, args.candidate_id, args.to, evidence=args.evidence
        )
        store.save(run)
        common.emit({"ok": True, "candidate": candidate})
        return 0

    return common.run_main(run)


if __name__ == "__main__":
    raise SystemExit(main())
