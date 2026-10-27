"""The benchmark clock must follow the labels, not a constant that falls behind."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from contracts.contracts import Ecosystem, EvidenceKind, TargetRef
from engine import checks, stage1
from engine.evidence import EvidenceBuilder
from eval.runner import FALLBACK_NOW, case_clock, run_case

TARGET = TargetRef(ecosystem=Ecosystem.PYPI, name="requests")


def test_clock_falls_back_when_a_case_carries_no_stamp():
    now, from_label = case_clock({"id": "a"})
    assert now == FALLBACK_NOW
    assert from_label is False


def test_clock_is_the_case_own_stamp():
    now, from_label = case_clock({"id": "a", "verified_at": "2026-11-05T09:30:00+00:00"})
    assert now == datetime(2026, 11, 5, 9, 30, tzinfo=UTC)
    assert from_label is True


def test_clock_ignores_an_unparseable_stamp():
    now, from_label = case_clock({"id": "a", "verified_at": "not a date"})
    assert now == FALLBACK_NOW
    assert from_label is False


def _aged_case(cid: str, released: str, verified_at: str | None) -> dict:
    case = {
        "id": cid,
        "label": "benign",
        "ecosystem": "pypi",
        "command": "pip install requests==2.31.0",
        "expected_verdict": "ALLOW",
        "facts": {
            "exists": True,
            "latest_version": "2.31.0",
            "latest_sha256": "f" * 64,
            "first_upload": "2015-01-01T00:00:00+00:00",
            "latest_upload": released,
        },
        "osv": {"malicious": False, "mal_ids": []},
    }
    if verified_at:
        case["verified_at"] = verified_at
    return case


def test_reverifying_one_case_does_not_move_another():
    """Regression: a run-wide clock taken from the newest stamp would re-date
    every case. Re-checking one package must not change any other verdict."""
    neighbour = _aged_case("b", released="2026-10-01T00:00:00+00:00", verified_at=None)
    before = run_case(neighbour)

    # A second case is verified far in the future. Under a shared clock this
    # would drag the neighbour's clock forward and flip it out of P6.
    _ = run_case(_aged_case("a", "2027-06-01T00:00:00+00:00", "2027-06-02T00:00:00+00:00"))
    after = run_case(neighbour)

    assert before.actual == after.actual
    assert before.matched_rules == after.matched_rules
    assert after.clock == FALLBACK_NOW


def test_each_case_is_judged_against_its_own_stamp():
    fresh = run_case(_aged_case("a", "2027-05-20T00:00:00+00:00", "2027-06-01T00:00:00+00:00"))
    stale = run_case(_aged_case("b", "2026-01-01T00:00:00+00:00", "2027-06-01T00:00:00+00:00"))
    # Same clock, different release dates: one release is recent, one is not.
    assert fresh.clock == stale.clock
    assert "new_release" in fresh.evidence_kinds
    assert "new_release" not in stale.evidence_kinds


def test_a_release_newer_than_the_clock_is_not_negative_age():
    """Regression: real PyPI dates sit after the hard-coded 2026-10-26 clock.

    An unclamped `(now - uploaded).days` goes negative, and every "younger than
    N days" comparison becomes true — so a decade-old package would look brand
    new and trip P6.
    """
    future = (FALLBACK_NOW + timedelta(days=40)).isoformat()
    facts = {
        "exists": True,
        "latest_version": "2.31.0",
        "first_upload": "2015-01-01T00:00:00+00:00",
        "latest_upload": future,
    }
    evidence = checks.check_age(TARGET, facts, EvidenceBuilder(), now=FALLBACK_NOW)
    ages = [e.observed["age_days"] for e in evidence]
    assert all(age >= 0 for age in ages), ages
    # Clamped to 0, the release still reads as recent, which is the honest answer
    # for a clock that is behind: we cannot say the release is old.
    assert EvidenceKind.NEW_RELEASE in {e.kind for e in evidence}


def test_stage1_with_a_label_derived_clock_sees_a_stable_package_as_old():
    now, _ = case_clock({"verified_at": "2026-12-01T00:00:00+00:00"})
    result = stage1.run(
        TARGET,
        registry_facts={
            "exists": True,
            "latest_version": "2.31.0",
            "latest_sha256": "e" * 64,
            "first_upload": "2015-01-01T00:00:00+00:00",
            "latest_upload": "2026-06-01T00:00:00+00:00",
        },
        osv_facts={"malicious": False, "mal_ids": []},
        now=now,
    )
    assert result.evidence == []
    assert result.decision.matched_rules == ("P9",)
