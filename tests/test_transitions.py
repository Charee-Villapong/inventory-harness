import json

import pytest

from tests.conftest import base_args
from tools import add_candidate, advance_candidate, build_matrix, common


@pytest.fixture()
def run_with_candidate(fake_env, capsys):
    assert build_matrix.main(base_args(fake_env, "--run-id", "r1")) == 0
    assert (
        add_candidate.main(
            base_args(fake_env, "r1", "refactoring", "repo-a") + ["--title", "t"]
        )
        == 0
    )
    capsys.readouterr()
    return fake_env


def _advance(env, to_state):
    return advance_candidate.main(base_args(env, "r1", "C-001") + ["--to", to_state])


def test_happy_path_chain(run_with_candidate, capsys):
    env = run_with_candidate
    for state in (
        "characterized",
        "in_progress",
        "reviewed",
        "scanned",
        "pushed",
        "reported",
    ):
        assert _advance(env, state) == 0, state
    capsys.readouterr()


def test_skipping_stages_is_refused(run_with_candidate, capsys):
    assert _advance(run_with_candidate, "pushed") == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False


def test_terminal_state_refuses_further_moves(run_with_candidate, capsys):
    env = run_with_candidate
    assert _advance(env, "rejected_as_spec") == 0
    assert _advance(env, "characterized") == 1
    capsys.readouterr()


def test_decision_pending_detour_and_resume(run_with_candidate, capsys):
    env = run_with_candidate
    assert _advance(env, "characterized") == 0
    assert _advance(env, "in_progress") == 0
    assert _advance(env, "decision_pending") == 0
    # Cannot jump sideways out of decision_pending...
    assert _advance(env, "reviewed") == 1
    # ...but can resume to the state it came from.
    assert _advance(env, "in_progress") == 0
    assert _advance(env, "reviewed") == 0
    capsys.readouterr()


def test_unknown_state_refused(run_with_candidate, capsys):
    assert _advance(run_with_candidate, "bogus") == 1
    capsys.readouterr()


def test_common_level_invalid_transition_raises(fake_env):
    config = common.load_config(fake_env.config_path)
    run = common.new_run(
        "rx", config.enabled_viewpoints(), common.discover_targets(config)
    )
    candidate = common.add_candidate(run, "refactoring", "repo-a", "t")
    with pytest.raises(common.HarnessError):
        common.advance_candidate(run, candidate["id"], "reported")
