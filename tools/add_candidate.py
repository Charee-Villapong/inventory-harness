"""Stage tool: register one candidate in a run.

The candidate enters state ``found`` and is linked to its
(viewpoint, target) cell. The cell itself stays pending until it is
marked with the mark-cell tool.

Usage: python -m tools.add_candidate RUN_ID VIEWPOINT TARGET --title T
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
    parser.add_argument("--title", required=True)
    common.add_common_args(parser)
    args = parser.parse_args(argv)

    def run() -> int:
        store = common.RunStore(args.state_dir)
        run = store.load(args.run_id)
        candidate = common.add_candidate(run, args.viewpoint, args.target, args.title)
        store.save(run)
        common.emit({"ok": True, "candidate": candidate})
        return 0

    return common.run_main(run)


if __name__ == "__main__":
    raise SystemExit(main())
