"""Evidence requirements on candidate transitions (spec: team rollout).

Transitions into reviewed / scanned / pushed / reported must carry an
evidence reference, recorded in the candidate history:

- reviewed  -> review result reference (non-empty)
- scanned   -> pre-push scan record (non-empty)
- pushed    -> commit hash (7-40 hex chars)
- reported  -> report reference (non-empty)

All other transitions keep working without evidence, and old state
files (whose history entries have no evidence key) must keep loading
and advancing: the change is purely additive.
"""

import json

import pytest

from tests.conftest import base_args
from tools import add_candidate, advance_candidate, build_matrix, common


@pytest.fixture()
def env_with_candidate(fake_env, capsys):
    assert build_matrix.main(base_args(fake_env, "--run-id", "r1")) == 0
    assert (
        add_candidate.main(
            base_args(fake_env, "r1", "refactoring", "repo-a") + ["--title", "t"]
        )
        == 0
    )
    capsys.readouterr()
    return fake_env


def _advance(env, to_state, evidence=None):
    args = base_args(env, "r1", "C-001") + ["--to", to_state]
    if evidence is not None:
        args += ["--evidence", evidence]
    return advance_candidate.main(args)


def _walk_to(env, state, capsys):
    """Walk C-001 up to `state`, supplying evidence where required."""
    path = ["characterized", "in_progress", "reviewed", "scanned", "pushed"]
    evidence = {
        "reviewed": "review: ok by reviewer",
        "scanned": "scan: clean",
        "pushed": "0123abc",
    }
    for step in path:
        assert _advance(env, step, evidence.get(step)) == 0, step
        if step == state:
            break
    capsys.readouterr()


def _load_candidate(env):
    store = common.RunStore(env.state_dir)
    return store.load("r1")["candidates"][0]


def test_reviewed_without_evidence_is_refused(env_with_candidate, capsys):
    env = env_with_candidate
    _walk_to(env, "in_progress", capsys)
    assert _advance(env, "reviewed") == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "evidence" in out["error"]


def test_scanned_without_evidence_is_refused(env_with_candidate, capsys):
    env = env_with_candidate
    _walk_to(env, "reviewed", capsys)
    assert _advance(env, "scanned") == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_reported_without_evidence_is_refused(env_with_candidate, capsys):
    env = env_with_candidate
    _walk_to(env, "pushed", capsys)
    assert _advance(env, "reported") == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_blank_evidence_is_refused(env_with_candidate, capsys):
    env = env_with_candidate
    _walk_to(env, "in_progress", capsys)
    assert _advance(env, "reviewed", evidence="   ") == 1
    capsys.readouterr()


@pytest.mark.parametrize(
    "bad_hash",
    ["abc", "xyz1234", "0123abg", "a" * 41, "0123 abc", ""],
)
def test_pushed_with_malformed_hash_is_refused(env_with_candidate, capsys, bad_hash):
    env = env_with_candidate
    _walk_to(env, "scanned", capsys)
    assert _advance(env, "pushed", evidence=bad_hash) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


@pytest.mark.parametrize("good_hash", ["0123abc", "0123ABC", "a" * 40])
def test_pushed_with_valid_hash_is_recorded(env_with_candidate, capsys, good_hash):
    env = env_with_candidate
    _walk_to(env, "scanned", capsys)
    assert _advance(env, "pushed", evidence=good_hash) == 0
    capsys.readouterr()
    entry = _load_candidate(env)["history"][-1]
    assert entry["to"] == "pushed"
    assert entry["evidence"]["kind"] == "commit"
    assert entry["evidence"]["ref"] == good_hash


def test_evidence_is_left_in_history(env_with_candidate, capsys):
    env = env_with_candidate
    _walk_to(env, "pushed", capsys)
    assert _advance(env, "reported", evidence="report: chat 2026-11-07") == 0
    capsys.readouterr()
    history = _load_candidate(env)["history"]
    by_state = {entry["to"]: entry for entry in history}
    assert by_state["reviewed"]["evidence"] == {
        "kind": "review",
        "ref": "review: ok by reviewer",
    }
    assert by_state["scanned"]["evidence"]["kind"] == "scan"
    assert by_state["reported"]["evidence"]["kind"] == "report"
    # Transitions without an evidence rule keep the plain entry shape.
    assert "evidence" not in by_state["characterized"]


def test_transitions_without_evidence_rule_still_work(env_with_candidate, capsys):
    env = env_with_candidate
    assert _advance(env, "characterized") == 0
    assert _advance(env, "decision_pending") == 0
    assert _advance(env, "characterized") == 0  # resume, still no evidence
    assert _advance(env, "rejected_as_spec") == 0
    capsys.readouterr()


def test_optional_evidence_on_free_transition_is_kept(env_with_candidate, capsys):
    env = env_with_candidate
    assert _advance(env, "characterized", evidence="tests: tests/test_x.py") == 0
    capsys.readouterr()
    entry = _load_candidate(env)["history"][-1]
    assert entry["evidence"]["ref"] == "tests: tests/test_x.py"


def test_common_level_missing_evidence_raises(fake_env):
    config = common.load_config(fake_env.config_path)
    run = common.new_run(
        "rx", config.enabled_viewpoints(), common.discover_targets(config)
    )
    candidate = common.add_candidate(run, "refactoring", "repo-a", "t")
    common.advance_candidate(run, candidate["id"], "characterized")
    common.advance_candidate(run, candidate["id"], "in_progress")
    with pytest.raises(common.HarnessError):
        common.advance_candidate(run, candidate["id"], "reviewed")
    with pytest.raises(common.HarnessError):
        common.advance_candidate(run, candidate["id"], "reviewed", evidence="  ")
    common.advance_candidate(run, candidate["id"], "reviewed", evidence="review: ok")
    assert run["candidates"][0]["state"] == "reviewed"


def test_old_state_shape_still_advances(fake_env):
    """A candidate whose history has no evidence keys (the shape written
    before this change) loads and advances as before."""
    config = common.load_config(fake_env.config_path)
    run = common.new_run(
        "rx", config.enabled_viewpoints(), common.discover_targets(config)
    )
    candidate = common.add_candidate(run, "refactoring", "repo-a", "t")
    for entry in candidate["history"]:
        assert "evidence" not in entry
    common.advance_candidate(run, candidate["id"], "characterized")
    common.advance_candidate(run, candidate["id"], "in_progress")
    assert candidate["state"] == "in_progress"
