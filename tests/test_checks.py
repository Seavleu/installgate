"""Checks turn facts into evidence. Severity is what the policy later keys on."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from contracts.contracts import Ecosystem, EvidenceKind, TargetRef
from engine import checks
from engine.evidence import EvidenceBuilder

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def days_ago(n: int) -> str:
    return (NOW - timedelta(days=n)).isoformat()


def target(name: str, ecosystem: Ecosystem = Ecosystem.PYPI, version: str | None = None):
    return TargetRef(ecosystem=ecosystem, name=name, version=version)


def test_missing_package_is_hard_evidence():
    evidence = checks.check_exists(target("nosuchpkg"), {"exists": False}, EvidenceBuilder())
    assert evidence is not None
    assert evidence.kind is EvidenceKind.NOT_FOUND
    assert evidence.severity == "hard"
    assert evidence.id == "EV-1"


def test_existing_package_produces_no_evidence():
    assert checks.check_exists(target("requests"), {"exists": True}, EvidenceBuilder()) is None


def test_new_project_and_new_release_are_soft():
    facts = {"exists": True, "first_upload": days_ago(3), "latest_upload": days_ago(1)}
    out = checks.check_age(target("brandnew"), facts, EvidenceBuilder(), now=NOW)
    kinds = {e.kind for e in out}
    assert kinds == {EvidenceKind.NEW_PROJECT, EvidenceKind.NEW_RELEASE}
    assert all(e.severity == "soft" for e in out)


def test_old_stable_package_has_no_age_evidence():
    facts = {"exists": True, "first_upload": days_ago(3000), "latest_upload": days_ago(200)}
    assert checks.check_age(target("requests"), facts, EvidenceBuilder(), now=NOW) == []


def test_osv_mal_record_is_hard():
    evidence = checks.check_osv_malicious(
        target("evil"), {"malicious": True, "mal_ids": ["MAL-2026-1"]}, EvidenceBuilder()
    )
    assert evidence is not None
    assert evidence.severity == "hard"
    assert evidence.trust == "deterministic"


def test_non_mal_vulnerabilities_do_not_fire():
    facts = {"malicious": False, "mal_ids": [], "other_ids": ["GHSA-xxxx"]}
    assert checks.check_osv_malicious(target("django"), facts, EvidenceBuilder()) is None


def test_typosquat_alone_is_soft(monkeypatch):
    monkeypatch.setattr(checks, "MIN_SNAPSHOT_NAMES", 1)
    monkeypatch.setattr(checks, "load_top_names", lambda eco: ("requests", "numpy"))
    facts = {"exists": True, "first_upload": days_ago(400)}
    out = checks.check_typosquat(target("reqeusts"), facts, EvidenceBuilder(), now=NOW)
    assert [e.kind for e in out] == [EvidenceKind.TYPOSQUAT]
    assert out[0].severity == "soft"
    assert out[0].observed["nearest_popular"] == "requests"


def test_typosquat_on_a_days_old_project_is_hard(monkeypatch):
    monkeypatch.setattr(checks, "MIN_SNAPSHOT_NAMES", 1)
    monkeypatch.setattr(checks, "load_top_names", lambda eco: ("requests", "numpy"))
    facts = {"exists": True, "first_upload": days_ago(2)}
    out = checks.check_typosquat(target("reqeusts"), facts, EvidenceBuilder(), now=NOW)
    kinds = [e.kind for e in out]
    assert EvidenceKind.TYPOSQUAT_NEW_PROJECT in kinds
    hard = [e for e in out if e.kind is EvidenceKind.TYPOSQUAT_NEW_PROJECT][0]
    assert hard.severity == "hard"


def test_exact_popular_name_is_not_a_typosquat(monkeypatch):
    monkeypatch.setattr(checks, "MIN_SNAPSHOT_NAMES", 1)
    monkeypatch.setattr(checks, "load_top_names", lambda eco: ("requests",))
    out = checks.check_typosquat(
        target("requests"),
        {"exists": True, "first_upload": days_ago(2)},
        EvidenceBuilder(),
        now=NOW,
    )
    assert out == []


def test_short_names_are_not_compared(monkeypatch):
    # At three characters a one-edit distance is normal between unrelated names.
    monkeypatch.setattr(checks, "MIN_SNAPSHOT_NAMES", 1)
    monkeypatch.setattr(checks, "load_top_names", lambda eco: ("six",))
    assert checks.check_typosquat(target("sax"), {"exists": True}, EvidenceBuilder(), now=NOW) == []


def test_truncated_reference_set_raises_instead_of_passing(monkeypatch):
    # A short list would otherwise return "no match", which reads as a clean result.
    monkeypatch.setattr(checks, "load_top_names", lambda eco: ("requests",))
    with pytest.raises(checks.SnapshotUnavailable):
        checks.check_typosquat(target("reqeusts"), {"exists": True}, EvidenceBuilder(), now=NOW)


def test_hf_pickle_is_soft_and_safetensors_sibling_is_info():
    facts = {
        "exists": True,
        "has_pickle": True,
        "pickle_files": ["pytorch_model.bin"],
        "has_safetensors": True,
        "safetensors_files": ["model.safetensors"],
    }
    out = checks.check_hf_format(
        target("org/model", Ecosystem.HUGGINGFACE), facts, EvidenceBuilder()
    )
    by_kind = {e.kind: e for e in out}
    assert by_kind[EvidenceKind.HF_PICKLE].severity == "soft"
    assert by_kind[EvidenceKind.HF_SAFETENSORS_SIBLING].severity == "info"


def test_safetensors_only_repo_is_clean():
    facts = {"exists": True, "has_pickle": False, "has_safetensors": True}
    assert (
        checks.check_hf_format(target("org/model", Ecosystem.HUGGINGFACE), facts, EvidenceBuilder())
        == []
    )


def test_base_tag_below_floor_is_hard():
    evidence = checks.check_runtime_floor(
        target("php", Ecosystem.DOCKER, "8.1.0"), EvidenceBuilder(), floors={"php": "8.2.20"}
    )
    assert evidence is not None
    assert evidence.severity == "hard"
    assert evidence.observed["patched_floor"] == "8.2.20"


def test_base_tag_at_floor_passes():
    assert (
        checks.check_runtime_floor(
            target("php", Ecosystem.DOCKER, "8.2.20"), EvidenceBuilder(), floors={"php": "8.2.20"}
        )
        is None
    )


def test_suffixed_tag_at_floor_passes():
    assert (
        checks.check_runtime_floor(
            target("python", Ecosystem.DOCKER, "3.11.9-slim"),
            EvidenceBuilder(),
            floors={"python": "3.11.9"},
        )
        is None
    )


def test_non_numeric_tag_is_not_comparable():
    # `latest` tells us nothing; other rules handle it rather than a false BLOCK.
    assert (
        checks.check_runtime_floor(
            target("php", Ecosystem.DOCKER, "latest"), EvidenceBuilder(), floors={"php": "8.2.20"}
        )
        is None
    )


def test_evidence_ids_increment_within_a_request():
    builder = EvidenceBuilder()
    first = checks.check_exists(target("a"), {"exists": False}, builder)
    second = checks.check_exists(target("b"), {"exists": False}, builder)
    assert (first.id, second.id) == ("EV-1", "EV-2")
