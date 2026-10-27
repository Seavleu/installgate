"""Stage 1 orchestration: facts in, evidence and a policy verdict out.

Pure and offline. The clients fetch; this module only arranges the checks, so the
benchmark and the unit tests can drive it from recorded facts with no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from contracts.contracts import Ecosystem, Evidence, TargetRef, Verdict

from engine import checks
from engine.evidence import EvidenceBuilder
from engine.policy import PolicyDecision, evaluate


@dataclass(frozen=True)
class Stage1Result:
    target: TargetRef
    evidence: list[Evidence]
    decision: PolicyDecision
    # Why a container tag could not be judged, when it could not be (FR-09).
    runtime_note: str | None = None

    @property
    def verdict(self) -> Verdict:
        return self.decision.verdict


def enrich_target(target: TargetRef, facts: dict[str, Any]) -> TargetRef:
    """Attach the resolved version and artefact hash the registry reports.

    Without this an otherwise clean package can never reach ALLOW, because P9
    requires a pinned artefact.
    """
    if not facts.get("exists"):
        return target

    version = target.version or facts.get("latest_version")
    sha = target.artifact_sha256 or facts.get("latest_sha256")
    # Only trust the registry hash when it describes the version we are checking.
    if target.version and facts.get("latest_version") != target.version:
        sha = target.artifact_sha256

    if version == target.version and sha == target.artifact_sha256:
        return target
    return TargetRef(
        ecosystem=target.ecosystem,
        name=target.name,
        version=version,
        artifact_sha256=sha,
    )


def gather_evidence(
    target: TargetRef,
    registry_facts: dict[str, Any],
    osv_facts: dict[str, Any] | None = None,
    known_maintainers: list[str] | None = None,
    now: datetime | None = None,
    builder: EvidenceBuilder | None = None,
) -> tuple[list[Evidence], str | None]:
    """Run every applicable check in a fixed order so EV ids are reproducible.

    Returns the evidence and, when a container tag could not be compared against
    a floor, the reason why.
    """
    now = now or datetime.now(UTC)
    builder = builder or EvidenceBuilder()
    evidence: list[Evidence] = []

    missing = checks.check_exists(target, registry_facts, builder)
    if missing is not None:
        # Nothing else is knowable about a package that is not there.
        return [missing], None

    if osv_facts:
        malicious = checks.check_osv_malicious(target, osv_facts, builder)
        if malicious is not None:
            evidence.append(malicious)

    evidence.extend(checks.check_typosquat(target, registry_facts, builder, now=now))
    evidence.extend(checks.check_age(target, registry_facts, builder, now=now))

    maintainer = checks.check_maintainers(
        target, registry_facts, builder, known_maintainers=known_maintainers, now=now
    )
    if maintainer is not None:
        evidence.append(maintainer)

    if target.ecosystem is Ecosystem.HUGGINGFACE:
        evidence.extend(checks.check_hf_format(target, registry_facts, builder))

    runtime_note: str | None = None
    if target.ecosystem is Ecosystem.DOCKER:
        floor = checks.check_runtime_floor(target, builder)
        if floor.evidence is not None:
            evidence.append(floor.evidence)
        if not floor.comparable:
            runtime_note = floor.reason

    return evidence, runtime_note


def run(
    target: TargetRef,
    registry_facts: dict[str, Any],
    osv_facts: dict[str, Any] | None = None,
    known_maintainers: list[str] | None = None,
    now: datetime | None = None,
    policy_path: str | None = None,
) -> Stage1Result:
    """The whole deterministic stage: enrich, gather evidence, apply policy."""
    enriched = enrich_target(target, registry_facts)
    evidence, runtime_note = gather_evidence(
        enriched, registry_facts, osv_facts, known_maintainers=known_maintainers, now=now
    )
    decision = evaluate(
        enriched,
        evidence,
        policy_path=policy_path,
        runtime_comparable=runtime_note is None,
    )
    return Stage1Result(
        target=enriched, evidence=evidence, decision=decision, runtime_note=runtime_note
    )
