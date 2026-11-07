"""Stage tool: record that one matrix cell has been investigated.

``--result candidates`` requires at least one candidate registered for
the cell (via add_candidate); ``--result none`` records that the cell
was checked and nothing was found.

Usage: python -m tools.mark_cell RUN_ID VIEWPOINT TARGET
       --result {candidates,none} [--note TEXT]
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
    parser.add_argument("viewpoint")
    parser.add_argument("target")
    parser.add_argument("--result", required=True, choices=["candidates", "none"])
    parser.add_argument("--note", default=None)
    common.add_common_args(parser)
    args = parser.parse_args(argv)

    def run() -> int:
        store = common.RunStore(args.state_dir)
        run = store.load(args.run_id)
        cell = common.mark_cell(
            run, args.viewpoint, args.target, args.result, note=args.note
        )
        store.save(run)
        common.emit({"ok": True, "cell": cell})
        return 0

    return common.run_main(run)


if __name__ == "__main__":
    raise SystemExit(main())
