"""T10: a substitute the model names itself never appears. No live network."""

from __future__ import annotations

from contracts.contracts import Ecosystem, TargetRef
from remediate.candidates import closed_set, propose

SHA_A = "a" * 64
SHA_B = "b" * 64


def _target(name: str, ecosystem: Ecosystem = Ecosystem.PYPI) -> TargetRef:
    return TargetRef(ecosystem=ecosystem, name=name)


def test_model_typed_name_never_appears() -> None:
    original = _target("reqeusts")
    candidates = closed_set(original, pins={"requests": ("2.32.3", SHA_A)})
    proposal = propose(
        original,
        "pip install reqeusts",
        candidates,
        selected_id="requests",
        recheck_evidence_ids=["EV-9"],
    )
    blob = proposal.remediation.model_dump_json() + (proposal.diff or "")
    assert proposal.remediation.status == "NO_SAFE_SUBSTITUTE"
    assert proposal.diff is None
    assert "requests" not in blob
    assert proposal.remediation.candidate is None


def test_pick_by_id_is_pinned_in_the_diff() -> None:
    original = _target("reqeusts")
    candidates = closed_set(
        original,
        pins={"requests": ("2.32.3", SHA_A), "unknown-pkg": ("1", "not-a-sha")},
        neighbours=["unknown-pkg", "flask"],
    )
    assert [item.id for item in candidates] == ["C1"]
    assert candidates[0].target.name == "requests"
    proposal = propose(
        original,
        "pip install reqeusts",
        candidates,
        selected_id="C1",
        recheck_evidence_ids=["EV-9"],
    )
    text = proposal.diff or ""
    assert text == (f"- pip install reqeusts\n+ pip install requests==2.32.3 --hash=sha256:{SHA_A}")
    assert proposal.remediation.status == "VERIFIED_SUBSTITUTE"
    assert proposal.remediation.candidate_source == "alias_map"
    assert proposal.remediation.selected_by == "llm_rank"
    assert "flask" not in text


def test_without_recheck_the_substitute_is_not_shown() -> None:
    original = _target("reqeusts")
    candidates = closed_set(original, pins={"requests": ("2.32.3", SHA_A)})
    proposal = propose(
        original,
        "pip install reqeusts",
        candidates,
        selected_id="C1",
        recheck_evidence_ids=[],
    )
    assert proposal.remediation.status == "VERIFICATION_UNAVAILABLE"
    assert proposal.diff is None
    assert proposal.remediation.candidate is None
    assert "requests" not in proposal.remediation.model_dump_json()


def test_one_candidate_is_chosen_by_rule() -> None:
    original = _target("org/model", Ecosystem.HUGGINGFACE)
    candidates = closed_set(
        original,
        pins={},
        hf_revision="main",
        hf_safetensors_sha256=SHA_B,
    )
    proposal = propose(
        original,
        "org/model",
        candidates,
        selected_id=None,
        recheck_evidence_ids=["EV-3"],
        bad_token="org/model",
    )
    assert candidates[0].source == "hf_sibling"
    assert proposal.remediation.selected_by == "rule"
    assert proposal.diff == (f"- org/model\n+ org/model@main --hash=sha256:{SHA_B}")


def test_docker_floor_is_pinned_by_digest() -> None:
    original = _target("php", Ecosystem.DOCKER)
    candidates = closed_set(
        original,
        pins={},
        docker_tag="8.3.14",
        docker_sha256=SHA_A,
    )
    proposal = propose(
        original,
        "FROM php:8.1",
        candidates,
        selected_id="C1",
        recheck_evidence_ids=["EV-4"],
        bad_token="php:8.1",
    )
    assert candidates[0].source == "docker_patched_floor"
    assert proposal.diff == (f"- FROM php:8.1\n+ FROM php:8.3.14@sha256:{SHA_A}")
