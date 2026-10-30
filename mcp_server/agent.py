"""Agent-facing extras on top of GateVerdict. Does not change the frozen contract."""

from __future__ import annotations

import json

from contracts.contracts import Ecosystem, GateVerdict, Verdict
from engine.parsers import ParseError, parse_command


def pinned_command(verdict: GateVerdict) -> str | None:
    """Copy-paste install for ALLOW. Version pin only — no --hash (deps would fail)."""
    if verdict.final_verdict is not Verdict.ALLOW or not verdict.target.version:
        return None
    target = verdict.target
    if target.ecosystem is Ecosystem.PYPI:
        return f"pip install {target.name}=={target.version}"
    if target.ecosystem is Ecosystem.NPM:
        return f"npm install {target.name}@{target.version}"
    return None


def substitute_command(verdict: GateVerdict) -> str | None:
    rem = verdict.remediation
    if rem is None or rem.status != "VERIFIED_SUBSTITUTE" or rem.candidate is None:
        return None
    candidate = rem.candidate
    if not candidate.version:
        return None
    if candidate.ecosystem is Ecosystem.PYPI:
        return f"pip install {candidate.name}=={candidate.version}"
    if candidate.ecosystem is Ecosystem.NPM:
        return f"npm install {candidate.name}@{candidate.version}"
    return None


def decided_by(verdict: GateVerdict) -> str:
    if verdict.final_verdict == verdict.policy_verdict:
        return "policy"
    return "lattice"


def parse_hint(command: str) -> str | None:
    try:
        targets = parse_command(command)
    except ParseError as exc:
        return str(exc)
    if len(targets) != 1:
        names = ", ".join(item.name for item in targets)
        return f"one package per check, got {len(targets)}: {names}"
    return None


def payload(verdict: GateVerdict, command: str) -> dict[str, object]:
    data: dict[str, object] = json.loads(verdict.model_dump_json())
    data["pinned_command"] = pinned_command(verdict)
    data["substitute_command"] = substitute_command(verdict)
    data["decided_by"] = decided_by(verdict)
    if verdict.failed_closed and not verdict.evidence:
        data["error"] = parse_hint(command) or "check failed closed"
    return data
