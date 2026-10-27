"""Loads policy.yaml and turns evidence into a policy verdict.

Deterministic and model-free: the same evidence always yields the same verdict.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from contracts.contracts import Ecosystem, Evidence, EvidenceKind, TargetRef, Verdict

POLICY_PATH = Path(__file__).parent / "policy.yaml"

# How much each severity contributes to the 0..1 risk score the router uses to
# decide whether a REVIEW is worth escalating to the Ultra tier.
_SEVERITY_WEIGHT = {"info": 0.0, "soft": 0.25, "hard": 1.0}


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    verdict: Verdict
    any_of: frozenset[EvidenceKind]
    requires_no_evidence: bool
    requires_pinned: bool


@dataclass(frozen=True)
class PolicyDecision:
    verdict: Verdict
    risk_score: float
    matched_rules: tuple[str, ...]
    policy_version: str


class PolicyError(RuntimeError):
    """The policy file is unusable. Callers must fail closed to REVIEW."""


def _parse_rule(raw: dict[str, Any]) -> Rule:
    try:
        kinds = frozenset(EvidenceKind(k) for k in (raw.get("any_of") or []))
    except ValueError as exc:
        raise PolicyError(f"rule {raw.get('id')} names an unknown evidence kind: {exc}") from exc
    try:
        verdict = Verdict(raw["verdict"])
    except (KeyError, ValueError) as exc:
        raise PolicyError(f"rule {raw.get('id')} has no valid verdict") from exc
    return Rule(
        id=str(raw.get("id", "?")),
        description=str(raw.get("description", "")),
        verdict=verdict,
        any_of=kinds,
        requires_no_evidence=bool(raw.get("requires_no_evidence")),
        requires_pinned=bool(raw.get("requires_pinned")),
    )


@functools.lru_cache(maxsize=1)
def load_policy(path: str | None = None) -> tuple[tuple[Rule, ...], str, Verdict]:
    target = Path(path) if path else POLICY_PATH
    if not target.exists():
        raise PolicyError(f"policy file missing: {target}")
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    rules = tuple(_parse_rule(r) for r in (data.get("rules") or []))
    if not rules:
        raise PolicyError("policy file defines no rules")
    version = str(data.get("version", "unknown"))
    try:
        default = Verdict(data.get("default_verdict", "REVIEW"))
    except ValueError as exc:
        raise PolicyError("default_verdict is not a valid verdict") from exc
    return rules, version, default


def risk_score(evidence: list[Evidence]) -> float:
    """0..1. Any hard evidence saturates; soft findings accumulate but stay below 1."""
    if not evidence:
        return 0.0
    if any(e.severity == "hard" for e in evidence):
        return 1.0
    total = sum(_SEVERITY_WEIGHT.get(e.severity, 0.0) for e in evidence)
    return min(round(total, 3), 0.95)


def is_pinned(target: TargetRef) -> bool:
    """Same rule as the contract: version + sha256, or a Hugging Face revision."""
    return bool(target.version and target.artifact_sha256) or (
        target.ecosystem is Ecosystem.HUGGINGFACE and target.revision is not None
    )


def evaluate(
    target: TargetRef,
    evidence: list[Evidence],
    policy_path: str | None = None,
) -> PolicyDecision:
    """Evaluate every rule; the strictest match sets the verdict.

    A check that could not run (a floating tag, an image with no floors, an
    ecosystem with no typosquat reference set) arrives as check_unavailable
    evidence, which P10 turns into REVIEW. We lack knowledge, not evidence, so
    it never produces a BLOCK (FR-09).
    """
    rules, version, default = load_policy(policy_path)
    kinds = {e.kind for e in evidence}
    pinned = is_pinned(target)

    matched: list[str] = []
    matched_verdicts: list[Verdict] = []

    for rule in rules:
        if rule.requires_no_evidence:
            # P9: a clean ALLOW needs zero findings of any severity and a pinned
            # artefact. A check that did not run is itself a finding (P10).
            if evidence or (rule.requires_pinned and not pinned):
                continue
        elif not (rule.any_of & kinds):
            continue
        elif rule.requires_pinned and not pinned:
            continue

        matched.append(rule.id)
        matched_verdicts.append(rule.verdict)

    # The strictest matched rule wins. Starting from the default and only ever
    # raising would make ALLOW unreachable, since REVIEW already outranks it.
    if not matched:
        verdict = default
    else:
        verdict = max(matched_verdicts, key=lambda v: v.rank)

    if verdict == Verdict.ALLOW and not pinned:
        verdict = Verdict.REVIEW

    # Guard rail mirroring the contract: BLOCK is only legitimate with hard
    # deterministic evidence behind it.
    if verdict == Verdict.BLOCK and not any(
        e.severity == "hard" and e.trust == "deterministic" for e in evidence
    ):
        verdict = Verdict.REVIEW

    return PolicyDecision(
        verdict=verdict,
        risk_score=risk_score(evidence),
        matched_rules=tuple(matched),
        policy_version=version,
    )
