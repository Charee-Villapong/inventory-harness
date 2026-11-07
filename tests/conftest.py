import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def fake_env(tmp_path):
    """A tiny fake world: two repos, one excluded repo, one non-repo
    directory, and an extra target, wired up in a temp config."""
    mirrors = tmp_path / "mirrors"
    for name in ("repo-a", "repo-b", "deadline-ledger"):
        (mirrors / name / ".git").mkdir(parents=True)
    (mirrors / "not-a-repo").mkdir()
    extras = tmp_path / "custom-skills"
    extras.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "targets": {
                    "mirrors_dir": str(mirrors),
                    "extra_targets": [{"name": "custom-skills", "path": str(extras)}],
                    "exclude": ["deadline-ledger"],
                },
                "viewpoints": [
                    {"id": "refactoring", "label": "r", "enabled": True},
                    {"id": "md-redundancy", "label": "m", "enabled": True},
                    {"id": "disabled-vp", "label": "d", "enabled": False},
                ],
            }
        ),
        encoding="utf-8",
    )
    return SimpleNamespace(
        tmp_path=tmp_path,
        mirrors=mirrors,
        config_path=config_path,
        state_dir=tmp_path / "state",
    )


def base_args(env, *extra):
    return [
        "--config",
        str(env.config_path),
        "--state-dir",
        str(env.state_dir),
        *extra,
    ]
