"""One check for HTTP, the CLI, and MCP (T11). Returns a GateVerdict and stops.

Does not install the package and does not run the substitute command.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from typing import Literal

import httpx
from contracts.contracts import (
    Ecosystem,
    Evidence,
    EvidenceKind,
    ExplanationSentence,
    GateVerdict,
    Outcome,
    TargetRef,
    Verdict,
)
from engine.cache import Cache
from engine.clients import UpstreamError, huggingface, npm, osv, pypi
from engine.evidence import EvidenceBuilder
from engine.parsers import ParseError, parse_command
from engine.policy import PolicyError, evaluate, load_policy
from engine.stage1 import run as stage1_run
from remediate.candidates import ALIASES, Proposal, closed_set, propose
from router.receipt import build_receipt
from router.tavily import search
from router.tiers import RouteResult, route
from validator.citations import validate as validate_citations
from validator.failclosed import FailClosedState
from validator.failclosed import apply as apply_failclosed
from validator.lattice import combine

from mcp_server.spend import add_spend, mark_capped, over_cap, reset_capped, was_capped

_log = logging.getLogger("installgate.mcp")

_FETCH = {
    Ecosystem.PYPI: pypi.fetch,
    Ecosystem.NPM: npm.fetch,
    Ecosystem.HUGGINGFACE: huggingface.fetch,
}
_INVALID = TargetRef(ecosystem=Ecosystem.PYPI, name="invalid")

StageHook = Callable[[dict[str, object]], None]


class _Stages:
    """Reports each finished stage to an optional hook. Progress only; never a verdict."""

    def __init__(self, hook: StageHook | None) -> None:
        self._hook = hook
        self._last = time.perf_counter()

    def __call__(self, stage: str, status: str, detail: str) -> None:
        now = time.perf_counter()
        ms, self._last = int((now - self._last) * 1000), now
        if self._hook is not None:
            self._hook({"stage": stage, "status": status, "detail": detail, "ms": ms})


def _cache() -> Cache:
    path = os.environ.get("CACHE_PATH", "./.cache/installgate.sqlite")
    return Cache(path)


def _policy_version() -> str:
    try:
        return load_policy()[1]
    except PolicyError:
        return "unknown"


def _closed(
    target: TargetRef,
    version: str,
    *,
    next_action: Literal["proceed", "use_substitute", "ask_human", "abort"] = "ask_human",
) -> GateVerdict:
    return GateVerdict(
        request_id=uuid.uuid4().hex,
        target=target,
        policy_version=version,
        policy_verdict=Verdict.REVIEW,
        final_verdict=Verdict.REVIEW,
        outcome=Outcome.REVIEW,
        risk_score=0.0,
        failed_closed=True,
        evidence=[],
        next_action=next_action,
    )


def _tone(verdict: Verdict) -> str:
    return {Verdict.ALLOW: "ok", Verdict.REVIEW: "warn", Verdict.BLOCK: "bad"}[verdict]


def _logged(verdict: GateVerdict) -> GateVerdict:
    payload: dict[str, object] = {
        "request_id": verdict.request_id,
        "stage": "check",
        "final_verdict": verdict.final_verdict.value,
        "failed_closed": verdict.failed_closed,
    }
    _log.info(json.dumps(payload, separators=(",", ":")))
    return verdict


def _engine_only(
    deterministic_only_ms: int,
    tavily_calls: int,
    explanation: tuple[ExplanationSentence, ...] = (),
) -> RouteResult:
    """Keep the policy verdict and do not call the model."""
    return RouteResult(
        llm_verdict=Verdict.ALLOW,
        added_targets=(),
        explanation=explanation,
        receipt=build_receipt(
            [],
            deterministic_only_ms=deterministic_only_ms,
            tavily_calls=tavily_calls,
        ),
        failed_closed=False,
    )


def gap_only(evidence: list[Evidence]) -> bool:
    """True when the only findings are unimplemented checks (P10)."""
    return bool(evidence) and all(item.kind is EvidenceKind.CHECK_UNAVAILABLE for item in evidence)


def _gap_sentences(evidence: list[Evidence]) -> tuple[ExplanationSentence, ...]:
    sentences: list[ExplanationSentence] = []
    for item in evidence:
        if item.kind is not EvidenceKind.CHECK_UNAVAILABLE:
            continue
        reason = str(item.observed.get("reason") or "unavailable")
        sentences.append(
            ExplanationSentence(
                text=f"A check could not run ({reason}) [{item.id}]",
                evidence_ids=[item.id],
            )
        )
    return tuple(sentences)


async def check(command: str, on_stage: StageHook | None = None) -> GateVerdict:
    """Parse one install command and return the gate verdict. Never runs it."""
    reset_capped()
    report = _Stages(on_stage)
    version = _policy_version()
    state = FailClosedState()
    try:
        targets = parse_command(command)
    except ParseError as exc:
        state.record("parse", exc)
        report("parse", "bad", f"{exc} · fail closed to REVIEW")
        return _logged(_closed(_INVALID, version, next_action="abort"))
    if len(targets) != 1:
        names = ", ".join(item.name for item in targets)
        state.record("parse", f"one package per check, got {len(targets)}: {names}")
        report("parse", "bad", f"one package per check, got {len(targets)}: {names}")
        return _logged(_closed(targets[0] if targets else _INVALID, version, next_action="abort"))

    target = targets[0]
    report(
        "parse",
        "ok",
        f"{target.ecosystem.value} · {target.name} · {target.version or 'unpinned'}",
    )
    cache = _cache()
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient() as client:
            fetch = _FETCH.get(target.ecosystem)
            if fetch is None:
                state.record("fetch", f"no metadata client for {target.ecosystem.value}")
                report("registry", "bad", "no metadata client · fail closed to REVIEW")
                return _logged(_closed(target, version))
            try:
                facts = await fetch(client, target, cache)
                pin = facts.get("pin_version") or facts.get("latest_version")
                latest = facts.get("latest_version")
                if facts.get("exists") and pin and latest and pin != latest:
                    registry_detail = f"exists · {pin} for this Python"
                elif facts.get("exists"):
                    registry_detail = f"exists · latest {latest}"
                else:
                    registry_detail = "not found"
                report(
                    "registry",
                    "ok" if facts.get("exists") else "bad",
                    registry_detail,
                )
                osv_facts = await osv.fetch(client, target, cache)
                mal = osv_facts.get("mal_ids") or []
                report(
                    "osv",
                    "bad" if mal else "ok",
                    f"MAL- record: {', '.join(map(str, mal))}" if mal else "no MAL- record",
                )
            except UpstreamError as exc:
                state.record("fetch", exc)
                report("registry", "bad", "upstream error · fail closed to REVIEW")
                return _logged(_closed(target, version))

            stage = stage1_run(target, facts, osv_facts)
            evidence = list(stage.evidence)
            kinds = sorted({item.kind.value for item in evidence})
            report(
                "checks",
                _tone(stage.verdict),
                f"{len(evidence)} finding{'s' * (len(evidence) != 1)}: {', '.join(kinds)}"
                if evidence
                else "no findings",
            )
            tavily_calls = 0
            unimplemented = gap_only(evidence)
            # shortcut: clean ALLOW skips Tavily; a gap is not a human decision
            if stage.verdict != Verdict.ALLOW and not unimplemented:
                found = await search(stage.target, start_id=len(evidence) + 1)
                evidence.extend(found.evidence)
                tavily_calls = found.calls
                if found.failed_closed:
                    state.record("tavily", "search failed")
                report(
                    "tavily",
                    "warn" if found.failed_closed else "ok",
                    f"{len(found.evidence)} web reports · untrusted, never hard"
                    if not found.failed_closed
                    else "search failed · stays REVIEW at least",
                )
            else:
                report(
                    "tavily",
                    "skip",
                    "skipped: unimplemented check" if unimplemented else "skipped: clean result",
                )
            decision = evaluate(stage.target, evidence)
            report(
                "policy",
                _tone(decision.verdict),
                f"{', '.join(decision.matched_rules) or 'no rule'} → {decision.verdict.value}"
                f" · risk {decision.risk_score:.2f}",
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            # shortcut: Nano may name extra targets, but this check only gates the parsed one
            if decision.verdict == Verdict.ALLOW:
                routed = _engine_only(elapsed_ms, tavily_calls)
            elif unimplemented:
                routed = _engine_only(elapsed_ms, tavily_calls, _gap_sentences(evidence))
            elif over_cap():
                mark_capped()
                routed = _engine_only(elapsed_ms, tavily_calls)
            else:
                routed = await route(
                    policy_verdict=decision.verdict,
                    risk_score=decision.risk_score,
                    evidence_ids=[item.id for item in evidence],
                    evidence=evidence,
                    command=command,
                    deterministic_only_ms=elapsed_ms,
                    tavily_calls=tavily_calls,
                )
                add_spend(routed.receipt.total_cost_usd)
            if routed.failed_closed:
                state.record("route", "model call failed")
            calls = routed.receipt.calls
            if calls:
                report(
                    "model",
                    "warn" if routed.failed_closed else "ok",
                    " → ".join(
                        f"{c.tier.value} {c.prompt_tokens + c.completion_tokens} tok" for c in calls
                    )
                    + (" · a call failed, stays REVIEW at least" if routed.failed_closed else ""),
                )
            else:
                report(
                    "model",
                    "skip",
                    "skipped: daily budget spent"
                    if was_capped()
                    else "skipped: clean ALLOW needs no model call"
                    if decision.verdict == Verdict.ALLOW
                    else "skipped: unimplemented check"
                    if unimplemented
                    else "no model call",
                )
            cited = validate_citations(list(routed.explanation), evidence)
            lattice = combine(decision.verdict, routed.llm_verdict, evidence)
            final = apply_failclosed(lattice.final, state, evidence)
            report(
                "validate",
                "warn" if state.failed else _tone(final),
                f"{len(cited.kept)} cited · {cited.dropped + routed.dropped_sentences} dropped"
                f" · stricter-of → {final.value}" + (" · failed closed" if state.failed else ""),
            )

            remediation = None
            outcome = Outcome(final.value)
            next_action: Literal["proceed", "use_substitute", "ask_human", "abort"] = (
                "proceed" if final == Verdict.ALLOW else "ask_human"
            )
            if unimplemented and final != Verdict.ALLOW:
                next_action = "abort"
                report("substitute", "skip", "skipped: unimplemented check")
            elif final != Verdict.ALLOW:
                proposal = await _substitute(client, cache, command, stage.target, evidence, state)
                remediation = proposal.remediation
                if remediation.status == "VERIFIED_SUBSTITUTE":
                    outcome = Outcome.VERIFIED_SUBSTITUTE
                    next_action = "use_substitute"
                verified = remediation.status == "VERIFIED_SUBSTITUTE" and remediation.candidate
                report(
                    "substitute",
                    "ok" if verified else "warn",
                    f"{remediation.candidate.name} · pinned · re-checked"
                    if verified and remediation.candidate
                    else remediation.status.lower().replace("_", " "),
                )
            else:
                report("pin", "ok", f"{stage.target.name}=={stage.target.version}")

            return _logged(
                GateVerdict(
                    request_id=uuid.uuid4().hex,
                    target=stage.target,
                    policy_version=decision.policy_version,
                    policy_verdict=decision.verdict,
                    llm_verdict=lattice.llm_applied,
                    final_verdict=final,
                    outcome=outcome,
                    risk_score=decision.risk_score,
                    failed_closed=state.failed,
                    evidence=evidence,
                    explanation=cited.kept,
                    dropped_sentences=cited.dropped + routed.dropped_sentences,
                    next_action=next_action,
                    remediation=remediation,
                    receipt=routed.receipt,
                )
            )
    finally:
        cache.close()


async def _substitute(
    client: httpx.AsyncClient,
    cache: Cache,
    command: str,
    original: TargetRef,
    evidence: list[Evidence],
    state: FailClosedState,
) -> Proposal:
    pins: dict[str, tuple[str, str]] = {}
    alias = ALIASES.get(original.name)
    if alias is not None:
        renamed = original.model_copy(
            update={"name": alias, "version": None, "artifact_sha256": None}
        )
        try:
            facts = await _FETCH[renamed.ecosystem](client, renamed, cache)
        except UpstreamError as exc:
            state.record("recheck", exc)
            facts = {}
        if facts.get("pin_version") and facts.get("pin_sha256"):
            version, digest = facts.get("pin_version"), facts.get("pin_sha256")
        else:
            version, digest = facts.get("latest_version"), facts.get("latest_sha256")
        if facts.get("exists") and isinstance(version, str) and isinstance(digest, str):
            pins[alias] = (version, digest)

    candidates = closed_set(original, pins=pins)
    recheck_ids: list[str] = []
    if len(candidates) == 1:
        chosen = candidates[0].target
        try:
            facts = await _FETCH[chosen.ecosystem](client, chosen, cache)
            osv_facts = await osv.fetch(client, chosen, cache)
            recheck = stage1_run(chosen, facts, osv_facts)
        except UpstreamError as exc:
            state.record("recheck", exc)
            recheck = None
        if recheck is not None and recheck.verdict == Verdict.ALLOW:
            record = EvidenceBuilder(start=len(evidence) + 1).build(
                EvidenceKind.RECHECK_PASSED,
                source="pypi",
                trust="deterministic",
                severity="info",
                target=chosen,
                observed={"policy_verdict": recheck.verdict.value},
            )
            evidence.append(record)
            recheck_ids = [record.id]

    return propose(
        original,
        command,
        candidates,
        selected_id=None,
        recheck_evidence_ids=recheck_ids,
    )
