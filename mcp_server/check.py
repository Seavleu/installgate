"""One check for HTTP, the CLI, and MCP (T11). Returns a GateVerdict and stops.

Does not install the package and does not run the substitute command.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Literal

import httpx
from contracts.contracts import (
    Ecosystem,
    Evidence,
    EvidenceKind,
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

from mcp_server.spend import add_spend, mark_capped, over_cap, reset_capped

_log = logging.getLogger("installgate.mcp")

_FETCH = {
    Ecosystem.PYPI: pypi.fetch,
    Ecosystem.NPM: npm.fetch,
    Ecosystem.HUGGINGFACE: huggingface.fetch,
}
_INVALID = TargetRef(ecosystem=Ecosystem.PYPI, name="invalid")


def _cache() -> Cache:
    path = os.environ.get("CACHE_PATH", "./.cache/installgate.sqlite")
    return Cache(path)


def _policy_version() -> str:
    try:
        return load_policy()[1]
    except PolicyError:
        return "unknown"


def _closed(target: TargetRef, version: str) -> GateVerdict:
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
        next_action="ask_human",
    )


def _logged(verdict: GateVerdict) -> GateVerdict:
    payload: dict[str, object] = {
        "request_id": verdict.request_id,
        "stage": "check",
        "final_verdict": verdict.final_verdict.value,
        "failed_closed": verdict.failed_closed,
    }
    _log.info(json.dumps(payload, separators=(",", ":")))
    return verdict


def _engine_only(deterministic_only_ms: int, tavily_calls: int) -> RouteResult:
    """The budget is spent. Keep the policy verdict and do not call the model."""
    return RouteResult(
        llm_verdict=Verdict.ALLOW,
        added_targets=(),
        explanation=(),
        receipt=build_receipt(
            [],
            deterministic_only_ms=deterministic_only_ms,
            tavily_calls=tavily_calls,
        ),
        failed_closed=False,
    )


async def check(command: str) -> GateVerdict:
    """Parse one install command and return the gate verdict. Never runs it."""
    reset_capped()
    version = _policy_version()
    state = FailClosedState()
    try:
        targets = parse_command(command)
    except ParseError as exc:
        state.record("parse", exc)
        return _logged(_closed(_INVALID, version))
    if len(targets) != 1:
        state.record("parse", "command must name one target")
        return _logged(_closed(targets[0] if targets else _INVALID, version))

    target = targets[0]
    cache = _cache()
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient() as client:
            fetch = _FETCH.get(target.ecosystem)
            if fetch is None:
                state.record("fetch", f"no metadata client for {target.ecosystem.value}")
                return _logged(_closed(target, version))
            try:
                facts = await fetch(client, target, cache)
                osv_facts = await osv.fetch(client, target, cache)
            except UpstreamError as exc:
                state.record("fetch", exc)
                return _logged(_closed(target, version))

            stage = stage1_run(target, facts, osv_facts)
            evidence = list(stage.evidence)
            tavily_calls = 0
            # shortcut: clean ALLOW skips Tavily; a web hit cannot lower a verdict
            if stage.verdict != Verdict.ALLOW:
                found = await search(stage.target, start_id=len(evidence) + 1)
                evidence.extend(found.evidence)
                tavily_calls = found.calls
                if found.failed_closed:
                    state.record("tavily", "search failed")
            decision = evaluate(stage.target, evidence)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            # shortcut: Nano may name extra targets, but this check only gates the parsed one
            if decision.verdict != Verdict.ALLOW and over_cap():
                mark_capped()
                routed = _engine_only(elapsed_ms, tavily_calls)
            else:
                routed = await route(
                    policy_verdict=decision.verdict,
                    risk_score=decision.risk_score,
                    evidence_ids=[item.id for item in evidence],
                    command=command,
                    deterministic_only_ms=elapsed_ms,
                    tavily_calls=tavily_calls,
                )
                add_spend(routed.receipt.total_cost_usd)
            if routed.failed_closed:
                state.record("route", "model call failed")
            cited = validate_citations(list(routed.explanation), evidence)
            lattice = combine(decision.verdict, routed.llm_verdict, evidence)
            final = apply_failclosed(lattice.final, state, evidence)

            remediation = None
            outcome = Outcome(final.value)
            next_action: Literal["proceed", "use_substitute", "ask_human"] = (
                "proceed" if final == Verdict.ALLOW else "ask_human"
            )
            if final != Verdict.ALLOW:
                proposal = await _substitute(client, cache, command, stage.target, evidence, state)
                remediation = proposal.remediation
                if remediation.status == "VERIFIED_SUBSTITUTE":
                    outcome = Outcome.VERIFIED_SUBSTITUTE
                    next_action = "use_substitute"

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
                    dropped_sentences=cited.dropped,
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
