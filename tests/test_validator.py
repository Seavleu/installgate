"""The validator floor: citations are enforced and the model can never loosen a verdict."""

from __future__ import annotations

from datetime import UTC, datetime

from contracts.contracts import Ecosystem, EvidenceKind, ExplanationSentence, TargetRef, Verdict
from engine.evidence import EvidenceBuilder
from validator import citations, failclosed, lattice

NOW = datetime(2026, 10, 26, tzinfo=UTC)
TARGET = TargetRef(ecosystem=Ecosystem.PYPI, name="reqeusts")


def make_evidence(count: int = 2, severity: str = "hard", trust: str = "deterministic"):
    builder = EvidenceBuilder()
    return [
        builder.build(
            EvidenceKind.TYPOSQUAT,
            source="pypi",
            trust=trust,
            severity=severity,
            target=TARGET,
            observed={"n": i},
            fetched_at=NOW,
        )
        for i in range(count)
    ]


# ---------- citations ----------
def test_sentence_without_a_citation_is_dropped():
    evidence = make_evidence(1)
    result = citations.validate(["This package looks dangerous."], evidence)
    assert result.kept == []
    assert result.dropped == 1


def test_sentence_citing_unknown_evidence_is_dropped():
    evidence = make_evidence(1)  # only EV-1 exists
    result = citations.validate(["Blocked because of [EV-7]."], evidence)
    assert result.kept == []
    assert "EV-7" in result.dropped_reasons[0]


def test_valid_citation_survives_and_ids_are_extracted():
    evidence = make_evidence(2)
    result = citations.validate(
        ["Name mimics a popular package [EV-1] and is new [EV-2]."], evidence
    )
    assert result.dropped == 0
    assert result.kept[0].evidence_ids == ["EV-1", "EV-2"]


def test_mixed_batch_keeps_only_cited_sentences():
    evidence = make_evidence(1)
    result = citations.validate(
        [
            ExplanationSentence(text="Typosquat of a popular name [EV-1].", evidence_ids=["EV-1"]),
            ExplanationSentence(text="Probably fine, trust me.", evidence_ids=["EV-1"]),
        ],
        evidence,
    )
    assert len(result.kept) == 1
    assert result.dropped == 1


def test_bare_ev_reference_without_brackets_counts():
    evidence = make_evidence(1)
    result = citations.validate(["See EV-1 for the registry record."], evidence)
    assert result.kept[0].evidence_ids == ["EV-1"]


# ---------- lattice ----------
def test_model_may_raise_allow_to_review():
    out = lattice.combine(Verdict.ALLOW, Verdict.REVIEW, make_evidence(1, severity="soft"))
    assert out.final is Verdict.REVIEW


def test_model_may_not_lower_a_block():
    evidence = make_evidence(1, severity="hard")
    out = lattice.combine(Verdict.BLOCK, Verdict.ALLOW, evidence)
    assert out.final is Verdict.BLOCK
    assert out.note is not None


def test_model_block_without_hard_evidence_is_clamped():
    out = lattice.combine(Verdict.ALLOW, Verdict.BLOCK, make_evidence(1, severity="soft"))
    assert out.final is Verdict.REVIEW
    assert out.clamped is True


def test_model_block_with_hard_evidence_matches_policy():
    evidence = make_evidence(1, severity="hard")
    out = lattice.combine(Verdict.BLOCK, Verdict.BLOCK, evidence)
    assert out.final is Verdict.BLOCK
    assert out.clamped is False


def test_no_model_verdict_leaves_policy_untouched():
    out = lattice.combine(Verdict.REVIEW, None, make_evidence(1, severity="soft"))
    assert out.final is Verdict.REVIEW
    assert out.llm_applied is None


# ---------- fail closed ----------
def test_error_turns_allow_into_review():
    state = failclosed.FailClosedState()
    with state.guard("pypi"):
        raise TimeoutError("registry timed out")
    assert state.failed
    assert failclosed.apply(Verdict.ALLOW, state) is Verdict.REVIEW


def test_clean_run_leaves_allow_alone():
    assert failclosed.apply(Verdict.ALLOW, failclosed.FailClosedState()) is Verdict.ALLOW


def test_block_backed_by_hard_evidence_survives_a_later_failure():
    state = failclosed.FailClosedState()
    state.record("tavily", "503")
    evidence = make_evidence(1, severity="hard")
    assert failclosed.apply(Verdict.BLOCK, state, evidence) is Verdict.BLOCK


def test_block_without_hard_evidence_degrades_on_failure():
    state = failclosed.FailClosedState()
    state.record("osv", "timeout")
    evidence = make_evidence(1, severity="soft")
    assert failclosed.apply(Verdict.BLOCK, state, evidence) is Verdict.REVIEW


def test_guard_swallows_the_error_and_records_the_stage():
    state = failclosed.FailClosedState()
    with state.guard("osv"):
        raise ValueError("bad json")
    assert state.failures[0].startswith("osv:")
