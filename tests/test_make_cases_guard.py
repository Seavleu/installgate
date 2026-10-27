"""make_cases writes fixtures. It must never write over real data.

It did once: a run replaced 50 fetched OSV advisories with MAL-PLACEHOLDER ids,
and the next benchmark would have reported recall against invented records.
"""

from __future__ import annotations

import json

import pytest
from eval import make_cases


@pytest.fixture
def cases_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(make_cases, "CASES_DIR", tmp_path)
    monkeypatch.setattr(make_cases, "PROVENANCE_PATH", tmp_path / "malicious.provenance.json")
    return tmp_path


def write(path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")


def test_a_missing_file_is_safe_to_write(cases_dir):
    assert make_cases.holds_real_data(cases_dir / "benign.jsonl") is None


def test_unverified_fixtures_may_be_regenerated(cases_dir):
    path = cases_dir / "benign.jsonl"
    write(path, [{"id": "benign-001", "verified_source": False}])
    assert make_cases.holds_real_data(path) is None


def test_a_verified_benign_file_is_protected(cases_dir):
    path = cases_dir / "benign.jsonl"
    write(
        path,
        [
            {"id": "benign-001", "verified_at": "2026-10-27T08:00:00+00:00"},
            {"id": "benign-002"},
        ],
    )
    reason = make_cases.holds_real_data(path)
    assert reason is not None and "verified_at" in reason


def test_a_verified_hallucinated_file_is_protected(cases_dir):
    path = cases_dir / "hallucinated.jsonl"
    write(path, [{"id": "hallucinated-001", "verified_at": "2026-10-27T08:00:00+00:00"}])
    assert make_cases.holds_real_data(path) is not None


def test_malicious_is_protected_by_its_provenance_file(cases_dir):
    path = cases_dir / "malicious.jsonl"
    write(path, [{"id": "malicious-001"}])
    assert make_cases.holds_real_data(path) is None
    (cases_dir / "malicious.provenance.json").write_text("{}", encoding="utf-8")
    assert "provenance" in (make_cases.holds_real_data(path) or "")


def test_a_malformed_line_does_not_look_like_verified_data(cases_dir):
    path = cases_dir / "typosquat.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    assert make_cases.holds_real_data(path) is None


def test_main_leaves_verified_files_alone(cases_dir, monkeypatch, capsys):
    verified = {"id": "benign-001", "verified_at": "2026-10-27T08:00:00+00:00"}
    write(cases_dir / "benign.jsonl", [verified])
    monkeypatch.setattr("sys.argv", ["make_cases"])

    make_cases.main()

    rows = [
        json.loads(line)
        for line in (cases_dir / "benign.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows == [verified], "verified benign cases were overwritten"
    assert "left alone" in capsys.readouterr().out
    # The unverified classes are still regenerated.
    assert (cases_dir / "typosquat.jsonl").exists()


def test_force_overwrites_verified_files(cases_dir, monkeypatch):
    write(cases_dir / "benign.jsonl", [{"id": "benign-001", "verified_at": "2026-10-27T08:00:00Z"}])
    monkeypatch.setattr("sys.argv", ["make_cases", "--force"])

    make_cases.main()

    rows = [
        json.loads(line)
        for line in (cases_dir / "benign.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 50
    assert all("verified_at" not in r for r in rows)
