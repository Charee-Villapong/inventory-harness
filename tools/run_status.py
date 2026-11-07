"""Stage tool: aggregate a run's state.

Prints cell counts by status, the still-pending cells, and candidate
counts by lifecycle state. Defaults to the latest run.

Usage: python -m tools.run_status [RUN_ID]
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
    parser.add_argument("run_id", nargs="?", default=None)
    common.add_common_args(parser)
    args = parser.parse_args(argv)

    def run() -> int:
        store = common.RunStore(args.state_dir)
        run_id = args.run_id or store.latest_run_id()
        common.emit(common.summarize(store.load(run_id)))
        return 0

    return common.run_main(run)


if __name__ == "__main__":
    raise SystemExit(main())
