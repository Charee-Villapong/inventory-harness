"""Stage tool: create a run and its viewpoint x target matrix.

Every cell starts as ``pending``; the run cannot be closed until all
cells are digested via the mark-cell tool.

Usage: python -m tools.build_matrix [--run-id ID] [--config PATH]
       [--state-dir DIR]
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
    parser.add_argument("--run-id", default=None, help="default: timestamped")
    common.add_common_args(parser)
    args = parser.parse_args(argv)

    def run() -> int:
        config = common.load_config(args.config)
        store = common.RunStore(args.state_dir)
        run_id = args.run_id or common.default_run_id()
        if store.path_for(run_id).is_file():
            raise common.HarnessError(f"run already exists: {run_id}")
        run = common.new_run(
            run_id,
            config.enabled_viewpoints(),
            common.discover_targets(config),
        )
        store.save(run)
        summary = common.summarize(run)
        summary["viewpoints"] = run["viewpoints"]
        summary["targets"] = [t["name"] for t in run["targets"]]
        common.emit(summary)
        return 0

    return common.run_main(run)


if __name__ == "__main__":
    raise SystemExit(main())
