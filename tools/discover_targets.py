"""Stage tool: enumerate the targets of a run.

Reads the config, lists every git repo under the mirrors dir plus the
extra targets, applies the exclusion list, and prints the result as
JSON. New repos are picked up automatically.

Usage: python -m tools.discover_targets [--config PATH]
"""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from tools import common
except ImportError:  # running as a plain script file
    import common  # type: ignore

    common.bootstrap()
    from tools import common


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=common.default_config_path())
    args = parser.parse_args(argv)

    def run() -> int:
        config = common.load_config(args.config)
        targets = common.discover_targets(config)
        common.emit({"targets": targets, "count": len(targets)})
        return 0

    return common.run_main(run)


if __name__ == "__main__":
    raise SystemExit(main())
