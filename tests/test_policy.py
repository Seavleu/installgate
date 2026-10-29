"""Policy P1-P10: the strictest match wins, and BLOCK needs hard deterministic evidence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from contracts.contracts import Ecosystem, EvidenceKind, TargetRef, Verdict
from engine import stage1
from engine.evidence import EvidenceBuilder
from engine.parsers import parse_dockerfile, parse_npm
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


def test_established_package_with_a_recent_release_is_allow():
    result = stage1.run(
        TargetRef(ecosystem=Ecosystem.PYPI, name="numpy"),
        registry_facts={
            "exists": True,
            "latest_version": "2.5.4",
            "latest_sha256": "b" * 64,
            "first_upload": "2006-08-26T00:00:00+00:00",
            "latest_upload": "2026-10-10T20:05:31+00:00",
        },
        osv_facts={"malicious": False, "mal_ids": []},
        now=NOW,
    )
    assert result.verdict is Verdict.ALLOW
    assert result.decision.matched_rules == ("P9",)
    assert result.evidence == []


def test_p9_regression_clean_pinned_package_reaches_allow_end_to_end():
    """Regression: evaluate() once seeded the verdict with the REVIEW default and
    only ever raised it, so P9 could match and still return REVIEW — every clean
    install would have asked for human review. Fixed in 3eab258."""
    result = stage1.run(
        TargetRef(ecosystem=Ecosystem.PYPI, name="requests"),
        registry_facts={
            "exists": True,
            "latest_version": "2.31.0",
            "latest_sha256": "c" * 64,
            "first_upload": "2015-01-01T00:00:00+00:00",
            "latest_upload": "2026-01-01T00:00:00+00:00",
            "maintainers": ["core"],
        },
        osv_facts={"malicious": False, "mal_ids": []},
        now=NOW,
    )
    assert result.verdict is Verdict.ALLOW
    assert result.decision.matched_rules == ("P9",)
    assert result.evidence == []


def _run_one(target, facts=None):
    return stage1.run(target, facts or {"exists": True}, now=NOW)


def _docker(tag, sha="d" * 64, name="php"):
    return TargetRef(ecosystem=Ecosystem.DOCKER, name=name, version=tag, artifact_sha256=sha)


def test_unlisted_runtime_branch_is_review_with_one_cited_evidence():
    # FR-09: no floor for the branch is absence of knowledge, so REVIEW, not BLOCK.
    result = _run_one(_docker("8.9.1"))
    assert result.verdict is Verdict.REVIEW
    assert result.decision.matched_rules == ("P10",)
    assert [e.id for e in result.evidence] == ["EV-1"]
    assert result.evidence[0].observed["reason"] == "no_floor_for_branch"


def test_comparable_runtime_still_reaches_allow():
    result = _run_one(_docker("8.2.35"))
    assert result.verdict is Verdict.ALLOW
    assert result.evidence == []


def test_php_8_3_apache_is_review_not_a_silent_pass():
    ref = parse_dockerfile("FROM php:8.3-apache\n")[0]
    result = _run_one(ref)
    assert result.verdict is Verdict.REVIEW
    assert result.decision.matched_rules == ("P10",)
    assert len(result.evidence) == 1
    assert result.evidence[0].observed["reason"] == "floating_tag"


def test_npm_lodash_is_review_with_one_cited_evidence():
    ref = parse_npm("npm install lodash@4.17.21")[0]
    result = _run_one(ref, {"exists": True, "latest_version": "4.17.21", "latest_sha256": "e" * 64})
    assert result.verdict is Verdict.REVIEW
    assert result.decision.matched_rules == ("P10",)
    assert len(result.evidence) == 1
    assert result.evidence[0].observed["reason"] == "typosquat_unsupported_ecosystem"


def test_clean_pinned_pypi_package_is_still_allow_with_zero_evidence():
    ref = TargetRef(
        ecosystem=Ecosystem.PYPI, name="requests", version="2.32.3", artifact_sha256="a" * 64
    )
    result = _run_one(
        ref,
        {
            "exists": True,
            "latest_version": "2.32.3",
            "latest_sha256": "a" * 64,
            "first_upload": "2012-01-01T00:00:00+00:00",
            "latest_upload": "2024-05-29T00:00:00+00:00",
        },
    )
    assert result.verdict is Verdict.ALLOW
    assert result.decision.matched_rules == ("P9",)
    assert result.evidence == []


def test_every_unavailable_reason_reviews_and_none_can_block():
    cases = {
        "no_floor_for_branch": _docker("8.9.1"),
        "floating_tag": _docker("latest"),
        "digest_only": TargetRef(ecosystem=Ecosystem.DOCKER, name="php", artifact_sha256="a" * 64),
        "image_not_in_table": _docker("1.0.0", name="vendor-image"),
    }
    for reason, ref in cases.items():
        result = _run_one(ref)
        assert result.verdict is Verdict.REVIEW, reason
        assert [e.observed["reason"] for e in result.evidence] == [reason]
        assert all(e.severity == "soft" for e in result.evidence)
