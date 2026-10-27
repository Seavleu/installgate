"""The stricter-of rule. The model can tighten a verdict; it can never loosen one.

ALLOW < REVIEW < BLOCK. `final = max(policy, llm)`, with one extra constraint:
BLOCK must come from deterministic policy evidence, never from the model.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.contracts import Evidence, Verdict


@dataclass(frozen=True)
class LatticeResult:
    final: Verdict
    llm_applied: Verdict | None
    clamped: bool
    note: str | None


def has_hard_deterministic(evidence: list[Evidence]) -> bool:
    return any(e.severity == "hard" and e.trust == "deterministic" for e in evidence)


def combine(
    policy_verdict: Verdict,
    llm_verdict: Verdict | None,
    evidence: list[Evidence],
) -> LatticeResult:
    """Resolve policy and model verdicts onto the lattice."""
    if llm_verdict is None:
        return LatticeResult(final=policy_verdict, llm_applied=None, clamped=False, note=None)

    applied = llm_verdict
    clamped = False
    note: str | None = None

    # The model may never produce BLOCK. Without hard deterministic evidence its
    # BLOCK is clamped to REVIEW; with such evidence, policy already says BLOCK.
    if llm_verdict == Verdict.BLOCK and not has_hard_deterministic(evidence):
        applied = Verdict.REVIEW
        clamped = True
        note = "model BLOCK clamped to REVIEW: no hard deterministic evidence"

    final = policy_verdict if policy_verdict.rank >= applied.rank else applied

    # The model lowering a verdict is silently ignored by max(), but say so.
    if applied.rank < policy_verdict.rank and note is None:
        note = f"model proposed {applied.value}; policy {policy_verdict.value} stands"

    return LatticeResult(final=final, llm_applied=applied, clamped=clamped, note=note)
