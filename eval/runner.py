"""Benchmark runner. Offline by default: every case carries its own registry facts.

    uv run python -m eval.runner

Writes eval/results.md. Nothing is installed, imported or executed from a case —
a case is a package name plus the metadata an API would have returned.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from contracts.contracts import Ecosystem, TargetRef, Verdict
from engine import stage1
from engine.parsers import ParseError, parse_dockerfile, parse_npm, parse_pip

CASES_DIR = Path(__file__).parent / "cases"
RESULTS_PATH = Path(__file__).parent / "results.md"

# The cases are dated, so the clock is fixed; otherwise "3 days old" drifts.
BENCHMARK_NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)

CASE_FILES = ["benign.jsonl", "malicious.jsonl", "hallucinated.jsonl", "typosquat.jsonl"]


VERDICTS = ("ALLOW", "REVIEW", "BLOCK")


@dataclass
class CaseResult:
    id: str
    label: str
    expected: str
    actual: str
    passed: bool
    latency_ms: float
    model_calls: int
    evidence_kinds: list[str]
    # Which policy rules fired. Without this a BLOCK tells you nothing about
    # whether the rule you meant to test is the one that caught the case.
    matched_rules: list[str]
    verified_source: bool
    error: str | None = None


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for name in CASE_FILES:
        path = CASES_DIR / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def target_from_case(case: dict[str, Any]) -> TargetRef:
    command = case["command"]
    ecosystem = case["ecosystem"]
    if ecosystem == "pypi":
        return parse_pip(command)[0]
    if ecosystem == "npm":
        return parse_npm(command)[0]
    if ecosystem == "docker":
        return parse_dockerfile(command)[0]
    if ecosystem == "huggingface":
        return TargetRef(ecosystem=Ecosystem.HUGGINGFACE, name=command.split()[-1])
    raise ParseError(f"unknown ecosystem: {ecosystem}")


def run_case(case: dict[str, Any]) -> CaseResult:
    started = time.perf_counter()
    try:
        target = target_from_case(case)
        result = stage1.run(
            target,
            registry_facts=case.get("facts") or {},
            osv_facts=case.get("osv"),
            now=BENCHMARK_NOW,
        )
        verdict = result.verdict.value
        kinds = [e.kind.value for e in result.evidence]
        rules = list(result.decision.matched_rules)
        error = None
    except Exception as exc:  # noqa: BLE001 - a crash must fail closed, not vanish
        verdict = Verdict.REVIEW.value
        kinds = []
        rules = []
        error = f"{type(exc).__name__}: {exc}"

    elapsed_ms = (time.perf_counter() - started) * 1000
    return CaseResult(
        id=case["id"],
        label=case["label"],
        expected=case["expected_verdict"],
        actual=verdict,
        passed=verdict == case["expected_verdict"],
        latency_ms=elapsed_ms,
        model_calls=0,  # Stage 1 is deterministic; the router is not on this path.
        evidence_kinds=kinds,
        matched_rules=rules,
        verified_source=bool(case.get("verified_source", True)),
        error=error,
    )


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(round((pct / 100) * (len(ordered) - 1))), len(ordered) - 1)
    return ordered[index]


def confusion(results: list[CaseResult]) -> dict[str, dict[str, int]]:
    """Expected verdict -> actual verdict -> count. Three classes, not two:
    collapsing REVIEW into "not blocked" hides a gate that pesters developers."""
    matrix = {e: dict.fromkeys(VERDICTS, 0) for e in VERDICTS}
    for r in results:
        if r.expected in matrix and r.actual in matrix[r.expected]:
            matrix[r.expected][r.actual] += 1
    return matrix


def rule_attribution(results: list[CaseResult]) -> dict[str, dict[str, int]]:
    """Per class, how often each policy rule fired. A malicious case caught by
    P1 (the package is gone) proves nothing about P2 (OSV says it is malware)."""
    out: dict[str, dict[str, int]] = {}
    for r in results:
        bucket = out.setdefault(r.label, {})
        for rule in r.matched_rules or ["(none)"]:
            bucket[rule] = bucket.get(rule, 0) + 1
    return out


def summarise(results: list[CaseResult], cases: list[dict[str, Any]]) -> dict[str, Any]:
    should_block = [r for r in results if r.expected == "BLOCK"]
    blocked_correctly = [r for r in should_block if r.actual == "BLOCK"]
    benign = [r for r in results if r.label == "benign"]
    false_blocks = [r for r in benign if r.actual == "BLOCK"]
    benign_reviews = [r for r in benign if r.actual == "REVIEW"]

    latencies = [r.latency_ms for r in results]
    placeholders = [c["id"] for c in cases if not c.get("verified_source", True)]
    ecosystems = sorted({str(c.get("ecosystem")) for c in cases})

    return {
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "block_recall": (len(blocked_correctly) / len(should_block)) if should_block else 0.0,
        "false_block_rate": (len(false_blocks) / len(benign)) if benign else 0.0,
        # Not a pass/fail metric, but the one a developer feels: how often a
        # known-good install still stops and asks a human.
        "benign_review_rate": (len(benign_reviews) / len(benign)) if benign else 0.0,
        "benign_reviews": benign_reviews,
        "zero_model_share": 1.0,
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "cost_per_check_usd": 0.0,
        "placeholders": placeholders,
        "ecosystems": ecosystems,
        "confusion": confusion(results),
        "attribution": rule_attribution(results),
        "errors": [r for r in results if r.error],
    }


def render(results: list[CaseResult], summary: dict[str, Any]) -> str:
    by_label: dict[str, list[CaseResult]] = {}
    for r in results:
        by_label.setdefault(r.label, []).append(r)

    ecosystems = ", ".join(summary["ecosystems"]) or "none"
    lines = [
        "# Benchmark results",
        "",
        "> **Run mode: deterministic-only.** Stage 1 is the whole pipeline here. The "
        "router, Tavily and the explanation stage are not exercised, so "
        "*checks with zero model calls* is trivially 100% and *cost per check* is "
        "trivially $0. Neither number means anything until the run goes through the "
        "router. Read them as placeholders, not results.",
        "",
        "Generated by `uv run python -m eval.runner`. Every case carries the registry "
        "metadata it needs, so the run is offline and a rerun gives the same numbers.",
        "",
        f"- Clock pinned to `{BENCHMARK_NOW.isoformat()}` (cases encode relative ages).",
        f"- Ecosystems covered: {ecosystems}.",
        f"- Cases: **{summary['total']}** | passed: **{summary['passed']}**",
        "",
        "## Headline metrics",
        "",
        "| Metric | Target | Result |",
        "| --- | --- | --- |",
        f"| Block recall | >= 95% | {summary['block_recall'] * 100:.1f}% |",
        f"| False-block rate (benign) | <= 2% | {summary['false_block_rate'] * 100:.1f}% |",
        f"| Review rate on benign | no target yet | {summary['benign_review_rate'] * 100:.1f}% |",
        f"| Checks with zero model calls | >= 70% | {summary['zero_model_share'] * 100:.0f}% "
        "(deterministic-only) |",
        f"| p50 latency | — | {summary['p50_ms']:.2f} ms |",
        f"| p95 latency | — | {summary['p95_ms']:.2f} ms |",
        f"| Cost per check | — | ${summary['cost_per_check_usd']:.5f} (deterministic-only) |",
        "",
        "Review rate on benign is the number a developer feels. A gate that blocks "
        "nothing but sends every second `pip install` to a human is still a gate "
        "nobody keeps switched on. Tune the 7/30-day thresholds against it.",
        "",
        "## Confusion matrix",
        "",
        "Rows are the expected verdict, columns what the policy returned.",
        "",
        "| expected \\ got | " + " | ".join(VERDICTS) + " |",
        "| --- | " + " | ".join("---" for _ in VERDICTS) + " |",
    ]
    for expected in VERDICTS:
        row = summary["confusion"][expected]
        if not any(row.values()):
            continue
        cells = " | ".join(str(row[got]) for got in VERDICTS)
        lines.append(f"| **{expected}** | {cells} |")

    lines += [
        "",
        "## Rule attribution",
        "",
        "Which policy rule actually fired, per case class. This is what separates a "
        "working check from a lucky one: a malicious package that was already pulled "
        "from the registry is caught by P1 (`not_found`) and says nothing about "
        "whether P2 (`osv_malicious`) works at all.",
        "",
        "| Class | Rules fired (count) |",
        "| --- | --- |",
    ]
    for label in ("benign", "malicious", "hallucinated", "typosquat"):
        bucket = summary["attribution"].get(label)
        if not bucket:
            continue
        rendered = ", ".join(
            f"`{rule}` ×{count}" for rule, count in sorted(bucket.items(), key=lambda kv: -kv[1])
        )
        lines.append(f"| {label} | {rendered} |")

    lines += [
        "",
        "## By case class",
        "",
        "| Class | Cases | Passed | Failed | Label source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for label in ("benign", "malicious", "hallucinated", "typosquat"):
        group = by_label.get(label, [])
        if not group:
            continue
        passed = sum(1 for r in group if r.passed)
        unverified = sum(1 for r in group if not r.verified_source)
        source = "verified" if not unverified else f"{unverified} unverified"
        lines.append(f"| {label} | {len(group)} | {passed} | {len(group) - passed} | {source} |")

    failures = [r for r in results if not r.passed]
    lines += ["", "## Failures", ""]
    if not failures:
        lines.append("None.")
    else:
        lines += [
            "| Case | Expected | Got | Rules | Evidence |",
            "| --- | --- | --- | --- | --- |",
        ]
        for r in failures[:50]:
            kinds = ", ".join(r.evidence_kinds) or "—"
            rules = ", ".join(r.matched_rules) or "—"
            lines.append(f"| `{r.id}` | {r.expected} | {r.actual} | {rules} | {kinds} |")
        if len(failures) > 50:
            lines.append(f"| … | | | | {len(failures) - 50} more |")

    reviews = summary["benign_reviews"]
    if reviews:
        lines += [
            "",
            "## Benign cases sent to review",
            "",
            "Not failures — these are correct under the policy, but each one is a "
            "developer interrupted on a package that turned out to be fine.",
            "",
            "| Case | Rules | Evidence |",
            "| --- | --- | --- |",
        ]
        for r in reviews[:30]:
            lines.append(
                f"| `{r.id}` | {', '.join(r.matched_rules) or '—'} | "
                f"{', '.join(r.evidence_kinds) or '—'} |"
            )

    if summary["errors"]:
        lines += ["", "## Errors (failed closed to REVIEW)", ""]
        for r in summary["errors"][:20]:
            lines.append(f"- `{r.id}`: {r.error}")

    if summary["placeholders"]:
        lines += [
            "",
            "## Not yet reportable",
            "",
            f"**{len(summary['placeholders'])} cases carry placeholder data** and are not "
            "evidence of real-world recall. Their `mal_ids` are invented identifiers, not "
            "records from osv.dev. Replace them with real OSV `MAL-` ids before quoting "
            "block recall anywhere outside this repository.",
            "",
            "Affected: "
            + ", ".join(f"`{p}`" for p in summary["placeholders"][:10])
            + (
                f" … and {len(summary['placeholders']) - 10} more"
                if len(summary["placeholders"]) > 10
                else ""
            ),
        ]

    return "\n".join(lines) + "\n"


def main() -> int:
    cases = load_cases()
    if not cases:
        print("no cases found in eval/cases/")
        return 1

    results = [run_case(c) for c in cases]
    summary = summarise(results, cases)
    RESULTS_PATH.write_text(render(results, summary), encoding="utf-8")

    print(f"{summary['passed']}/{summary['total']} cases passed")
    print(f"block recall       {summary['block_recall'] * 100:.1f}%")
    print(f"false-block rate   {summary['false_block_rate'] * 100:.1f}%")
    print(f"benign review rate {summary['benign_review_rate'] * 100:.1f}%")
    print(f"p50 / p95          {summary['p50_ms']:.2f} / {summary['p95_ms']:.2f} ms")
    for label, bucket in sorted(summary["attribution"].items()):
        rules = ", ".join(f"{r}x{c}" for r, c in sorted(bucket.items(), key=lambda kv: -kv[1]))
        print(f"  {label:<13} {rules}")
    print("NOTE: deterministic-only run; model-call and cost figures are not meaningful")
    if summary["placeholders"]:
        print(f"WARNING: {len(summary['placeholders'])} cases use placeholder OSV ids")
    print(f"wrote {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
