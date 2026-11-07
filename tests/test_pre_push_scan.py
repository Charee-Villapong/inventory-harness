"""Unit tests for tools/pre_push_scan.py.

Fixture-string based: detection, exclusion and literal handling are
exercised against canned text, with no dependency on a real repository.
Fixture secrets below are synthetic shapes, not real credentials.
"""

import json

from tools.pre_push_scan import (
    is_binary,
    is_excluded,
    load_local_literals,
    scan_text,
)

CLEAN = "normal source line\nanother harmless line\n"


def kinds_by_line(text, literals=()):
    hits = scan_text(text, list(literals))
    return {(hit["line"], hit["kind"]) for hit in hits}


def test_clean_text_has_no_hits():
    assert scan_text(CLEAN, []) == []


def test_email_detected_without_leaking_content():
    # Assembled at runtime so this file itself stays scan-clean.
    text = "contact: " + "someone" + "@" + "example.com" + "\n"
    hits = scan_text(text, [])
    assert [(h["line"], h["kind"]) for h in hits] == [(1, "email")]
    # The hit record must carry only line and kind, never the content.
    assert set(hits[0]) == {"line", "kind"}


def test_ipv4_detected():
    text = "host = " + "192.0.2." + "10" + "\n"
    assert (1, "ipv4") in kinds_by_line(text)


def test_token_prefixes_detected():
    samples = [
        "tok = ghp_" + "A" * 36,
        "tok = github_pat_" + "B" * 30,
        "tok = sk-" + "c" * 32,
        "key = AKIA" + "D" * 16,
    ]
    for sample in samples:
        assert (1, "token_prefix") in kinds_by_line(sample + "\n"), sample[:12]


def test_short_lookalikes_not_flagged_as_tokens():
    assert scan_text("sk-short\n", []) == []
    assert scan_text("ghp_tiny\n", []) == []


def test_private_key_header_detected():
    plain = "-----BEGIN " + "PRIVATE KEY-----\n"
    rsa = "-----BEGIN RSA " + "PRIVATE KEY-----\n"
    assert (1, "private_key_header") in kinds_by_line(plain)
    assert (1, "private_key_header") in kinds_by_line(rsa)
    assert scan_text("-----BEGIN CERTIFICATE-----\n", []) == []


def test_local_literal_detected_by_kind_only():
    hits = scan_text("the fixture word is present here\n", ["fixture word"])
    assert [(h["line"], h["kind"]) for h in hits] == [(1, "local_literal")]
    assert scan_text("nothing here\n", ["fixture word"]) == []


def test_one_hit_per_line_and_kind():
    text = "192.0.2." + "1 and " + "198.51.100." + "2 on one line\n"
    assert scan_text(text, []) == [{"line": 1, "kind": "ipv4"}]


def test_multiple_kinds_on_different_lines():
    text = "someone" + "@" + "example.com" + "\n" + "192.0.2." + "10" + "\n"
    assert kinds_by_line(text) == {(1, "email"), (2, "ipv4")}


def test_is_excluded():
    assert is_excluded(".venv/lib/python3/site.py")
    assert is_excluded("pkg/.venv/bin/tool")
    assert is_excluded("state/runs/monthly-20261107.json")
    assert is_excluded("scan-patterns.local.json")
    assert not is_excluded("tools/run_status.py")
    assert not is_excluded("statement.py")


def test_is_binary():
    assert is_binary(b"\x89PNG\r\n\x1a\n\x00\x00")
    assert not is_binary("plain text\n".encode("utf-8"))


def test_load_local_literals(tmp_path):
    path = tmp_path / "scan-patterns.local.json"
    path.write_text(json.dumps({"literals": ["alpha", "beta"]}), encoding="utf-8")
    assert load_local_literals(path) == ["alpha", "beta"]


def test_load_local_literals_missing_or_malformed(tmp_path):
    assert load_local_literals(tmp_path / "absent.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert load_local_literals(bad) == []
