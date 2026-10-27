"""Fail closed. Any error in the pipeline degrades to REVIEW, never to ALLOW.

The deterministic evidence gathered before the failure is kept: a partial answer
with its sources intact is more useful to a human than a bare error.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from contracts.contracts import Evidence, Verdict


@dataclass
class FailClosedState:
    """Collects failures seen while building one verdict."""

    failures: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.failures)

    def record(self, stage: str, error: BaseException | str) -> None:
        self.failures.append(f"{stage}: {error}")

    @contextmanager
    def guard(self, stage: str) -> Iterator[None]:
        """Run a stage; swallow its error and remember it."""
        try:
            yield
        except Exception as exc:  # noqa: BLE001 - deliberate: every stage fails closed
            self.record(stage, exc)


def apply(
    verdict: Verdict, state: FailClosedState, evidence: list[Evidence] | None = None
) -> Verdict:
    """Raise a verdict to at least REVIEW when any stage failed.

    A BLOCK backed by hard deterministic evidence survives a later failure — the
    evidence for it was already collected.
    """
    if not state.failed:
        return verdict
    if verdict == Verdict.BLOCK:
        has_hard = any(
            e.severity == "hard" and e.trust == "deterministic" for e in (evidence or [])
        )
        return Verdict.BLOCK if has_hard else Verdict.REVIEW
    return Verdict.REVIEW if verdict == Verdict.ALLOW else verdict
