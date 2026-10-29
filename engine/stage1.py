"""Stage 1 orchestration: facts in, evidence and a policy verdict out.

Pure and offline. The clients fetch; this module only arranges the checks, so the
benchmark and the unit tests can drive it from recorded facts with no network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from contracts.contracts import Ecosystem, Evidence, TargetRef, Verdict

from engine import checks
from engine.evidence import EvidenceBuilder
from engine.policy import PolicyDecision, evaluate

# A Hugging Face model sha is a 40-character git commit; anything else is not a pin.
_GIT_SHA = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class Stage1Result:
    target: TargetRef
    evidence: list[Evidence]
    decision: PolicyDecision

    @property
    def verdict(self) -> Verdict:
        return self.decision.verdict


def enrich_target(target: TargetRef, facts: dict[str, Any]) -> TargetRef:
    """Attach the resolved version and artefact hash the registry reports.

    Without this an otherwise clean package can never reach ALLOW, because P9
    requires a pinned artefact. A Hugging Face repo is pinned by git revision
    instead: the API's model `sha` fills `revision` when the target has none.
    """
    if not facts.get("exists"):
        return target

    if target.ecosystem is Ecosystem.HUGGINGFACE:
        sha = facts.get("sha")
        if target.revision is not None or not isinstance(sha, str) or not _GIT_SHA.fullmatch(sha):
            return target
        return TargetRef(ecosystem=target.ecosystem, name=target.name, revision=sha)

    version = target.version or facts.get("pin_version") or facts.get("latest_version")
    sha = target.artifact_sha256
    if sha is None and not target.version:
        # Unpinned: install the interpreter-compatible pin, not a newer
        # requires_python-incompatible latest (numpy 2.5.4 needs 3.12+).
        sha = facts.get("pin_sha256") or facts.get("latest_sha256")
    elif sha is None:
        # Only trust the registry hash when it describes the version we are checking.
        if facts.get("pin_version") == target.version:
            sha = facts.get("pin_sha256")
        if sha is None and facts.get("latest_version") == target.version:
            sha = facts.get("latest_sha256")

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
) -> list[Evidence]:
    """Run every applicable check in a fixed order so EV ids are reproducible.

    A check that could not run (a container tag with no comparable floor, an
    ecosystem with no typosquat reference set) contributes a soft
    check_unavailable record rather than silence.
    """
    now = now or datetime.now(UTC)
    builder = builder or EvidenceBuilder()
    evidence: list[Evidence] = []

    missing = checks.check_exists(target, registry_facts, builder)
    if missing is not None:
        # Nothing else is knowable about a package that is not there.
        return [missing]

    if osv_facts:
        malicious = checks.check_osv_malicious(target, osv_facts, builder)
        if malicious is not None:
            evidence.append(malicious)

    typosquat = checks.check_typosquat(target, registry_facts, builder, now=now)
    evidence.extend(typosquat.evidence)
    evidence.extend(checks.check_age(target, registry_facts, builder, now=now))

    maintainer = checks.check_maintainers(
        target, registry_facts, builder, known_maintainers=known_maintainers, now=now
    )
    if maintainer is not None:
        evidence.append(maintainer)

    if target.ecosystem is Ecosystem.HUGGINGFACE:
        evidence.extend(checks.check_hf_format(target, registry_facts, builder))

    if target.ecosystem is Ecosystem.DOCKER:
        floor = checks.check_runtime_floor(target, builder)
        if floor.evidence is not None:
            evidence.append(floor.evidence)

    return evidence


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
    evidence = gather_evidence(
        enriched, registry_facts, osv_facts, known_maintainers=known_maintainers, now=now
    )
    decision = evaluate(enriched, evidence, policy_path=policy_path)
    return Stage1Result(target=enriched, evidence=evidence, decision=decision)
