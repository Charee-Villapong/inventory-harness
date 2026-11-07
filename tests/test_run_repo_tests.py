"""Unit tests for tools/run_repo_tests.py.

Fixture-string based: the parser and the ok judgement are exercised
against canned pytest output, with no dependency on a real repository.
"""

from tools.run_repo_tests import is_ok, parse_pytest_output

ALL_PASS = """\
............                                                             [100%]
32 passed in 0.25s
"""

MIXED = """\
.FFs                                                                     [100%]
================================== FAILURES ===================================
_______________________________ test_broken ________________________________
    def test_broken():
>       assert 1 == 2
E       assert 1 == 2
=========================== short test summary info ============================
FAILED tests/test_sample.py::test_broken - assert 1 == 2
1 failed, 2 passed, 1 skipped in 1.23s
"""

WITH_ERROR = """\
E                                                                        [100%]
=========================== short test summary info ============================
ERROR tests/test_sample.py::test_fixture - RuntimeError: boom
2 passed, 1 error in 0.10s
"""

NO_TESTS = """\

no tests ran in 0.01s
"""

GARBAGE = "some unrelated output\nwith no summary at all\n"


def test_parse_all_pass():
    parsed = parse_pytest_output(ALL_PASS)
    assert parsed["error"] is None
    assert parsed["passed"] == 32
    assert parsed["failed"] == 0
    assert parsed["errors"] == 0
    assert parsed["skipped"] == 0
    assert parsed["total"] == 32
    assert parsed["duration_sec"] == 0.25
    assert parsed["failed_tests"] == []
    assert is_ok(parsed) is True


def test_parse_mixed_counts_and_failed_names():
    parsed = parse_pytest_output(MIXED)
    assert parsed["error"] is None
    assert parsed["passed"] == 2
    assert parsed["failed"] == 1
    assert parsed["skipped"] == 1
    assert parsed["total"] == 4
    assert parsed["duration_sec"] == 1.23
    assert parsed["failed_tests"] == ["tests/test_sample.py::test_broken"]
    assert is_ok(parsed) is False


def test_parse_error_count_plural_and_singular():
    parsed = parse_pytest_output(WITH_ERROR)
    assert parsed["passed"] == 2
    assert parsed["errors"] == 1
    assert parsed["total"] == 3
    assert parsed["failed_tests"] == ["tests/test_sample.py::test_fixture"]
    assert is_ok(parsed) is False
    plural = parse_pytest_output("3 passed, 2 errors in 0.50s\n")
    assert plural["errors"] == 2


def test_parse_no_tests_ran_is_abnormal():
    parsed = parse_pytest_output(NO_TESTS)
    assert parsed["total"] == 0
    assert parsed["error"] is not None
    assert is_ok(parsed) is False


def test_parse_missing_summary_is_abnormal():
    parsed = parse_pytest_output(GARBAGE)
    assert parsed["total"] == 0
    assert parsed["error"] is not None
    assert is_ok(parsed) is False


def test_failed_tests_capped_at_twenty():
    lines = "\n".join(f"FAILED tests/test_m.py::test_{i} - boom" for i in range(30))
    parsed = parse_pytest_output(lines + "\n30 failed in 2.00s\n")
    assert parsed["failed"] == 30
    assert len(parsed["failed_tests"]) == 20


def test_failed_tests_deduplicated():
    output = (
        "FAILED tests/test_m.py::test_a - boom\n"
        "FAILED tests/test_m.py::test_a - boom\n"
        "1 failed in 0.10s\n"
    )
    parsed = parse_pytest_output(output)
    assert parsed["failed_tests"] == ["tests/test_m.py::test_a"]


def test_skipped_only_is_not_ok_because_error_free_but_check_total():
    parsed = parse_pytest_output("5 skipped in 0.02s\n")
    assert parsed["total"] == 5
    assert parsed["error"] is None
    # Nothing failed, but is_ok only requires no failures/errors.
    assert is_ok(parsed) is True
