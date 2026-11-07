import json

from tests.conftest import base_args
from tools import add_candidate, build_matrix, close_run, mark_cell, run_status


def _build(env):
    assert build_matrix.main(base_args(env, "--run-id", "r1")) == 0


def _drain(capsys):
    capsys.readouterr()


def test_close_run_refused_while_cells_pending(fake_env, capsys):
    _build(fake_env)
    _drain(capsys)
    rc = close_run.main(base_args(fake_env, "r1"))
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert len(out["pending_cells"]) == 6


def test_mark_candidates_requires_a_candidate_first(fake_env, capsys):
    _build(fake_env)
    _drain(capsys)
    rc = mark_cell.main(
        base_args(fake_env, "r1", "refactoring", "repo-a") + ["--result", "candidates"]
    )
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_full_flow_to_close(fake_env, capsys):
    _build(fake_env)
    rc = add_candidate.main(
        base_args(fake_env, "r1", "refactoring", "repo-a")
        + ["--title", "duplicated helper"]
    )
    assert rc == 0
    _drain(capsys)
    cells = [
        ("refactoring", "repo-a", "candidates"),
        ("refactoring", "repo-b", "none"),
        ("refactoring", "custom-skills", "none"),
        ("md-redundancy", "repo-a", "none"),
        ("md-redundancy", "repo-b", "none"),
        ("md-redundancy", "custom-skills", "none"),
    ]
    for viewpoint, target, result in cells:
        rc = mark_cell.main(
            base_args(fake_env, "r1", viewpoint, target) + ["--result", result]
        )
        assert rc == 0, (viewpoint, target)
    _drain(capsys)
    rc = run_status.main(base_args(fake_env, "r1"))
    assert rc == 0
    status = json.loads(capsys.readouterr().out)
    assert status["pending_cells"] == []
    assert status["candidates_by_state"] == {"found": 1}
    rc = close_run.main(base_args(fake_env, "r1"))
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_state_survives_reload(fake_env, capsys):
    _build(fake_env)
    add_candidate.main(
        base_args(fake_env, "r1", "refactoring", "repo-a") + ["--title", "x"]
    )
    _drain(capsys)
    # A brand-new store object reading from disk sees the candidate:
    # this is what makes an interrupted run resumable.
    from tools import common

    store = common.RunStore(fake_env.state_dir)
    run = store.load("r1")
    assert run["candidates"][0]["title"] == "x"
    assert run["candidates"][0]["state"] == "found"
