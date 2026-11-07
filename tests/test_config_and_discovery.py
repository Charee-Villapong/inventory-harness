import json

import pytest

from tools import build_matrix, common, discover_targets


def test_duplicate_viewpoint_ids_rejected(fake_env):
    raw = json.loads(fake_env.config_path.read_text(encoding="utf-8"))
    raw["viewpoints"].append({"id": "refactoring", "enabled": True})
    fake_env.config_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(common.HarnessError):
        common.load_config(fake_env.config_path)


def test_discovery_excludes_and_skips_non_repos(fake_env, capsys):
    rc = discover_targets.main(["--config", str(fake_env.config_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    names = [t["name"] for t in out["targets"]]
    # deadline-ledger excluded; not-a-repo has no .git and is skipped;
    # the extra target is present.
    assert names == ["custom-skills", "repo-a", "repo-b"]


def test_new_repo_is_picked_up_automatically(fake_env, capsys):
    (fake_env.mirrors / "repo-new" / ".git").mkdir(parents=True)
    rc = discover_targets.main(["--config", str(fake_env.config_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "repo-new" in [t["name"] for t in out["targets"]]


def test_matrix_covers_enabled_viewpoints_only(fake_env, capsys):
    from tests.conftest import base_args

    rc = build_matrix.main(base_args(fake_env, "--run-id", "r1"))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["cells_total"] == 6  # 2 enabled viewpoints x 3 targets
    assert out["cells_by_status"] == {"pending": 6}
