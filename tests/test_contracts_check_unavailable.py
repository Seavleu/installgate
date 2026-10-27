"""T03b: check_unavailable evidence and the TargetRef.revision pin."""

from datetime import UTC, datetime
from typing import Any

import pytest
from contracts.contracts import (
    CHECK_UNAVAILABLE_REASONS,
    Ecosystem,
    Evidence,
    EvidenceKind,
    GateVerdict,
    TargetRef,
    Verdict,
)
from pydantic import ValidationError

NOW = datetime(2026, 10, 27, tzinfo=UTC)
TARGET = TargetRef(ecosystem=Ecosystem.DOCKER, name="php")
OBSERVED = {"reason": "no_floor_for_branch"}


def _evidence(
    severity: str, observed: dict[str, Any] | None = None, trust: str = "deterministic"
) -> Evidence:
    kind = EvidenceKind.CHECK_UNAVAILABLE
    observed = OBSERVED if observed is None else observed
    return Evidence(
        id="EV-1",
        kind=kind,
        source="policy_yaml",
        trust=trust,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        target=TARGET,
        observed=observed,
        fetched_at=NOW,
        content_hash=Evidence.compute_hash(kind.value, TARGET, observed, None),
    )


@pytest.mark.parametrize("severity", ["info", "soft"])
def test_check_unavailable_accepts_info_and_soft(severity: str) -> None:
    assert _evidence(severity).kind is EvidenceKind.CHECK_UNAVAILABLE


def test_check_unavailable_rejects_hard() -> None:
    with pytest.raises(ValidationError, match="check_unavailable"):
        _evidence("hard")


def _target(**extra: Any) -> TargetRef:
    return TargetRef(ecosystem=Ecosystem.HUGGINGFACE, name="org/model", **extra)


def test_revision_defaults_to_none_and_accepts_40_lowercase_hex() -> None:
    assert _target().revision is None
    assert _target(revision="a" * 40).revision == "a" * 40


@pytest.mark.parametrize("bad", ["a" * 64, "A" * 40, "a" * 39, "g" * 40, ""])
def test_revision_rejects_anything_but_40_lowercase_hex(bad: str) -> None:
    with pytest.raises(ValidationError):
        _target(revision=bad)


def test_artifact_sha256_is_unchanged() -> None:
    assert _target(artifact_sha256="b" * 64).artifact_sha256 == "b" * 64
    with pytest.raises(ValidationError):
        _target(artifact_sha256="b" * 40)


@pytest.mark.parametrize("reason", sorted(CHECK_UNAVAILABLE_REASONS))
def test_each_documented_reason_is_accepted(reason: str) -> None:
    assert _evidence("soft", {"reason": reason}).observed["reason"] == reason


@pytest.mark.parametrize("observed", [{"reason": "because"}, {}, {"reason": None}])
def test_unknown_or_missing_reason_is_rejected(observed: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="reason"):
        _evidence("soft", observed)


def test_hashes_of_targets_without_revision_are_unchanged_since_main() -> None:
    # Literals computed on origin/main before the revision field existed.
    docker = TargetRef(ecosystem=Ecosystem.DOCKER, name="php", version="8.2.1")
    assert (
        Evidence.compute_hash("not_found", docker, {"a": 1}, "https://x.example/")
        == "7de0d5e8deee55654d4be70e1d9db0a62dfdc953ea077d7f5fe5b91d0ab5dd66"
    )
    pypi = TargetRef(ecosystem=Ecosystem.PYPI, name="requests")
    assert (
        Evidence.compute_hash("new_project", pypi, {}, None)
        == "d6a23f8b37fec9d2b3c199f313095a7e2784b52e494642276942961d780c9d2d"
    )


def test_hash_changes_once_a_revision_is_set() -> None:
    bare = _target()
    pinned = _target(revision="a" * 40)
    assert Evidence.compute_hash("hf_pickle", bare, {}, None) != Evidence.compute_hash(
        "hf_pickle", pinned, {}, None
    )


def _allow(target: TargetRef) -> GateVerdict:
    return GateVerdict(
        request_id="r1",
        target=target,
        policy_version="test",
        policy_verdict=Verdict.ALLOW,
        final_verdict=Verdict.ALLOW,
        outcome="ALLOW",  # type: ignore[arg-type]
        risk_score=0.0,
        evidence=[],
        next_action="proceed",
    )


def test_allow_accepts_version_plus_sha256() -> None:
    _allow(
        TargetRef(
            ecosystem=Ecosystem.PYPI, name="requests", version="2.32.0", artifact_sha256="a" * 64
        )
    )


def test_allow_accepts_a_pinned_hugging_face_revision() -> None:
    _allow(_target(revision="a" * 40))


def test_allow_rejects_unpinned_hugging_face_and_revision_on_other_ecosystems() -> None:
    with pytest.raises(ValidationError, match="pinned"):
        _allow(_target())
    with pytest.raises(ValidationError, match="pinned"):
        _allow(TargetRef(ecosystem=Ecosystem.PYPI, name="requests", revision="a" * 40))
