"""Builds hashed Evidence with sequential EV-n ids.

Evidence is immutable once emitted: the content hash is computed over the
observed facts, so a mutated record fails the contract's own validator.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from contracts.contracts import Evidence, EvidenceKind, TargetRef

Source = Literal[
    "pypi", "npm", "osv", "huggingface", "docker_registry", "policy_yaml", "tavily", "sandbox"
]
Trust = Literal["deterministic", "retrieved_untrusted"]
Severity = Literal["info", "soft", "hard"]


class EvidenceBuilder:
    """Hands out EV-1, EV-2, … within one request."""

    def __init__(self, start: int = 1) -> None:
        self._next = start

    def build(
        self,
        kind: EvidenceKind,
        *,
        source: Source,
        trust: Trust,
        severity: Severity,
        target: TargetRef,
        observed: dict[str, Any] | None = None,
        source_url: str | None = None,
        fetched_at: datetime | None = None,
    ) -> Evidence:
        if trust == "retrieved_untrusted" and severity == "hard":
            raise ValueError("untrusted evidence can never be hard")
        payload = observed or {}
        evidence = Evidence(
            id=f"EV-{self._next}",
            kind=kind,
            source=source,
            trust=trust,
            severity=severity,
            target=target,
            observed=payload,
            source_url=source_url,
            fetched_at=fetched_at or datetime.now(UTC),
            content_hash=Evidence.compute_hash(kind.value, target, payload, source_url),
        )
        self._next += 1
        return evidence
