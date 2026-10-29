"""TTY view of a check. uv / ruff / cargo diagnostics, not JSON."""

from __future__ import annotations

import os
import re
import shutil
import textwrap

from contracts.contracts import Evidence, GateVerdict

STAGE_NAME = {
    "parse": "Parse target",
    "registry": "Registry metadata",
    "osv": "OSV.dev",
    "checks": "Deterministic checks",
    "tavily": "Tavily (untrusted)",
    "policy": "Policy",
    "model": "Nemotron · Token Factory",
    "validate": "Validator",
    "substitute": "Substitute",
    "pin": "Pin",
}
_GLYPH = {"ok": "✔", "warn": "▲", "bad": "✖", "skip": "–"}
_ANSI = {
    "ok": "\033[32m",
    "warn": "\033[33m",
    "bad": "\033[31m",
    "skip": "\033[90m",
    "dim": "\033[90m",
    "link": "\033[36m",
    "reset": "\033[0m",
    "bold": "\033[1m",
}
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_RULE = {
    "not_found": "P1",
    "osv_malicious": "P2",
    "runtime_below_floor": "P3",
    "typosquat_new_project": "P4",
    "typosquat": "P5",
    "new_project": "P6",
    "new_release": "P6",
    "hf_pickle": "P7",
    "maintainer_change": "P8",
    "check_unavailable": "P10",
}
_SKIP_OBS = frozenset({"first_upload", "latest_upload"})


def _on() -> bool:
    return not os.environ.get("NO_COLOR")


def _c(tone: str, text: str) -> str:
    if not _on() or tone not in _ANSI:
        return text
    return f"{_ANSI[tone]}{text}{_ANSI['reset']}"


def _plain(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _cols() -> int:
    return max(60, min(shutil.get_terminal_size((88, 24)).columns, 96))


def _words(value: str) -> str:
    return value.replace("_", " ")


def _money(value: float) -> str:
    if value == 0:
        return "$0"
    if value < 0.01:
        return f"${value:.5f}"
    return f"${value:.2f}"


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


def _row(left: str, right: str) -> str:
    gap = _cols() - len(_plain(left)) - len(_plain(right))
    if gap < 1:
        return f"{left} {right}"
    return f"{left}{' ' * gap}{right}"


def _wrap(prefix: str, text: str) -> None:
    width = max(32, _cols() - len(_plain(prefix)))
    lines = textwrap.wrap(text, width=width) or [""]
    print(f"{prefix}{lines[0]}")
    pad = " " * len(_plain(prefix))
    for line in lines[1:]:
        print(f"{pad}{line}")


def print_header(command: str) -> None:
    print(f"{_c('dim', 'Checking')} {_c('bold', command)}", flush=True)


def print_stage(event: dict[str, object]) -> None:
    status = str(event.get("status", "skip"))
    glyph = _c(status, _GLYPH.get(status, "·"))
    name = STAGE_NAME.get(str(event.get("stage", "")), str(event.get("stage", "")))
    detail = _clip(str(event.get("detail", "")), 48)
    raw_ms = event.get("ms")
    ms = f"{raw_ms if isinstance(raw_ms, int) else 0}ms"
    left = f"  {glyph} {_c('bold', f'{name:<22}')}  {_c('dim', detail)}"
    print(_row(left, _c("skip", ms)), flush=True)


def print_verdict(verdict: GateVerdict, command: str, elapsed_ms: int) -> None:
    tone = {"ALLOW": "ok", "REVIEW": "warn", "BLOCK": "bad"}[verdict.final_verdict.value]
    kind = {"ALLOW": "success", "REVIEW": "warning", "BLOCK": "error"}[verdict.final_verdict.value]
    target = verdict.target
    pin = f"{target.name}=={target.version}" if target.version else target.name
    code = _rule_id(verdict)
    label = f"{kind}[{code}]" if code else kind
    print()
    print(_c(tone, f"{label}: {verdict.final_verdict.value} {pin}"))
    print(
        _c(
            "dim",
            f"  {target.ecosystem.value} · risk {verdict.risk_score:.2f} · "
            f"{_words(verdict.outcome.value).lower()}",
        )
    )
    if verdict.failed_closed:
        print(_c("warn", "warning: a lookup failed, so this stays a review"))

    for item in verdict.evidence:
        _span(item)

    if not verdict.evidence:
        print(_c("dim", "  no findings · model skipped"))

    for sentence in verdict.explanation:
        _wrap(f"  {_c('skip', 'note:')} ", _cited(sentence.text, sentence.evidence_ids))
    if verdict.dropped_sentences:
        dropped = f"{verdict.dropped_sentences} sentence(s) dropped (no evidence id)"
        print(_c("skip", f"  note: {dropped}"))

    _help(verdict, command)
    print(_c("dim", f"  note: {_receipt(verdict, elapsed_ms)}"))


def _rule_id(verdict: GateVerdict) -> str:
    want = "hard" if verdict.final_verdict.value == "BLOCK" else "soft"
    for item in verdict.evidence:
        if item.severity == want:
            return _RULE.get(item.kind.value, "")
    if verdict.evidence:
        return _RULE.get(verdict.evidence[0].kind.value, "")
    return ""


def _observed(observed: dict[str, object]) -> str:
    parts = []
    for key, item in observed.items():
        if key in _SKIP_OBS:
            continue
        raw = item if isinstance(item, str) else str(item)
        if key in {"title", "snippet", "sha256", "artifact_sha256"}:
            raw = _clip(raw, 56)
        parts.append(f"{key}: {raw}")
        if len(parts) == 4:
            break
    return " · ".join(parts)


def _span(item: Evidence) -> None:
    if item.severity == "hard":
        tone = "bad"
    elif item.severity == "soft":
        tone = "warn"
    else:
        tone = "skip"
    web = " · web" if item.trust == "retrieved_untrusted" else ""
    finding = _words(item.kind.value)
    print(f"  {_c(tone, '×')} {finding}")
    head = f"{item.id} {item.severity}{web} · {item.source}"
    print(f"   {_c('dim', '╭─[')} {_c('link', head)} {_c('dim', ']')}")
    facts = _observed(item.observed)
    if facts:
        _wrap(f"   {_c('dim', '│')}  ", facts)
    print(_c("dim", "   ╰──"))


def _cited(text: str, ids: list[str]) -> str:
    if all(eid in text for eid in ids):
        return text
    return f"{text} [{', '.join(ids)}]"


def _help(verdict: GateVerdict, command: str) -> None:
    rem = verdict.remediation
    if rem is not None and rem.status == "VERIFIED_SUBSTITUTE" and rem.approved_requirement:
        safe = (
            command.replace(rem.original.name, rem.approved_requirement)
            if rem.original.name in command
            else rem.approved_requirement
        )
        source = _words(rem.candidate_source or "closed set")
        ids = ", ".join(rem.recheck_evidence_ids)
        print(_c("ok", f"  help: use substitute ({source} · re-checked {ids})"))
        print(_c("bad", f"    - {command}"))
        _wrap(f"    {_c('ok', '+')} ", safe)
        note = rem.equivalence_note or ""
        print(_c("dim", f"  note: {note}".rstrip()))
        return
    if verdict.final_verdict.value != "ALLOW":
        print(_c("warn", "  help: no safe substitute in the closed candidate set"))
        print(_c("dim", "  note: ask a human which package was meant, then check that name"))
        return
    if verdict.target.version:
        pin = f"{verdict.target.name}=={verdict.target.version}"
        sha = verdict.target.artifact_sha256
        cmd = f"pip install {pin}" + (f" --hash=sha256:{sha}" if sha else "")
        print(_c("ok", f"  help: {cmd}"))
        print(_c("dim", "  note: pinned artefact. Confirm to run."))


def _receipt(verdict: GateVerdict, elapsed_ms: int) -> str:
    took = f"{elapsed_ms / 1000:.2f}s"
    receipt = verdict.receipt
    if receipt is None or not receipt.calls:
        return f"no model · $0 · {took}"
    chain = " → ".join(
        f"{call.tier.value.capitalize()} {call.prompt_tokens + call.completion_tokens} tok"
        for call in receipt.calls
    )
    tavily = f" · Tavily {receipt.tavily_calls}" if receipt.tavily_calls else ""
    saved = f"−{receipt.savings_pct:.0f}% vs all-Ultra"
    return f"{chain} · {_money(receipt.total_cost_usd)} ({saved}){tavily} · {took}"
