"""Policy P1-P9: the strictest match wins, and BLOCK needs hard deterministic evidence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from contracts.contracts import Ecosystem, EvidenceKind, TargetRef, Verdict
from engine.evidence import EvidenceBuilder
from engine.policy import evaluate, risk_score

NOW = datetime(2026, 10, 26, tzinfo=UTC)
PINNED = TargetRef(
    ecosystem=Ecosystem.PYPI, name="requests", version="2.31.0", artifact_sha256="a" * 64
)
UNPINNED = TargetRef(ecosystem=Ecosystem.PYPI, name="requests")


def ev(kind: EvidenceKind, severity: str, trust: str = "deterministic", target=PINNED):
    return EvidenceBuilder().build(
        kind, source="pypi", trust=trust, severity=severity, target=target, fetched_at=NOW
    )


def test_p9_clean_pinned_target_is_allowed():
    decision = evaluate(PINNED, [])
    assert decision.verdict is Verdict.ALLOW
    assert "P9" in decision.matched_rules


def test_clean_but_unpinned_is_review_not_allow():
    # TOCTOU: an unpinned ALLOW can resolve to a different artefact at install time.
    assert evaluate(UNPINNED, []).verdict is Verdict.REVIEW


def test_p1_missing_package_blocks():
    decision = evaluate(PINNED, [ev(EvidenceKind.NOT_FOUND, "hard")])
    assert decision.verdict is Verdict.BLOCK
    assert "P1" in decision.matched_rules


def test_p2_osv_malicious_blocks():
    assert evaluate(PINNED, [ev(EvidenceKind.OSV_MALICIOUS, "hard")]).verdict is Verdict.BLOCK


def test_p3_runtime_below_floor_blocks():
    docker = TargetRef(ecosystem=Ecosystem.DOCKER, name="php", version="8.1.0")
    evidence = [ev(EvidenceKind.RUNTIME_BELOW_FLOOR, "hard", target=docker)]
    assert evaluate(docker, evidence).verdict is Verdict.BLOCK


def test_p4_typosquat_on_new_project_blocks():
    evidence = [
        ev(EvidenceKind.TYPOSQUAT, "soft"),
        ev(EvidenceKind.TYPOSQUAT_NEW_PROJECT, "hard"),
    ]
    decision = evaluate(PINNED, evidence)
    assert decision.verdict is Verdict.BLOCK
    assert {"P4", "P5"} <= set(decision.matched_rules)


def test_p5_typosquat_alone_only_reviews():
    assert evaluate(PINNED, [ev(EvidenceKind.TYPOSQUAT, "soft")]).verdict is Verdict.REVIEW


def test_p6_release_age_alone_never_blocks():
    evidence = [ev(EvidenceKind.NEW_PROJECT, "soft"), ev(EvidenceKind.NEW_RELEASE, "soft")]
    assert evaluate(PINNED, evidence).verdict is Verdict.REVIEW


def test_p7_hf_pickle_reviews():
    assert evaluate(PINNED, [ev(EvidenceKind.HF_PICKLE, "soft")]).verdict is Verdict.REVIEW


def test_p8_maintainer_change_reviews():
    assert evaluate(PINNED, [ev(EvidenceKind.MAINTAINER_CHANGE, "soft")]).verdict is Verdict.REVIEW


def test_strictest_match_wins_over_softer_rules():
    evidence = [
        ev(EvidenceKind.NEW_PROJECT, "soft"),
        ev(EvidenceKind.HF_PICKLE, "soft"),
        ev(EvidenceKind.OSV_MALICIOUS, "hard"),
    ]
    assert evaluate(PINNED, evidence).verdict is Verdict.BLOCK


def test_block_without_hard_evidence_degrades_to_review():
    # Untrusted web evidence can never carry a BLOCK on its own.
    soft_web = ev(EvidenceKind.WEB_REPORT, "soft", trust="retrieved_untrusted")
    assert evaluate(PINNED, [soft_web]).verdict is Verdict.REVIEW


def test_info_evidence_still_blocks_a_clean_allow():
    # P9 requires zero findings of any severity, info included.
    assert evaluate(PINNED, [ev(EvidenceKind.HF_SAFETENSORS_SIBLING, "info")]).verdict is (
        Verdict.REVIEW
    )


@pytest.mark.parametrize(
    "severities,expected",
    [([], 0.0), (["info"], 0.0), (["soft"], 0.25), (["soft", "soft"], 0.5), (["hard"], 1.0)],
)
def test_risk_score_scales_with_severity(severities, expected):
    evidence = [ev(EvidenceKind.NEW_PROJECT, s) for s in severities]
    assert risk_score(evidence) == expected
