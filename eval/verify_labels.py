"""Refresh case labels against the live registry. ONLINE — run by hand, never in CI.

    uv run python -m eval.verify_labels --dry-run     # show what it would fetch
    uv run python -m eval.verify_labels               # fetch and rewrite the cases

Why this exists, and why it is not part of the runner: the benchmark must be
deterministic (NFR-10), so `runner.py` stays offline and reads facts baked into
each case. But two labels decay. A hallucinated name is only hallucinated until
someone registers it, and a benign package's real release dates move every time
it ships. R7 asks for label provenance, so each case this script touches gets a
`verified_at` stamp and a `verified_source` flag; the runner warns when a stamp
is older than MAX_LABEL_AGE_DAYS.

What it does NOT do:
  * install, import or execute anything — it reads the PyPI JSON API only;
  * invent a label — if a hallucinated name turns out to exist, the case is
    flagged for a human, not silently relabelled or deleted;
  * touch the malicious cases — those come from OSV via fetch_osv_malicious.py.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from engine.clients import HEADERS, TIMEOUT, UpstreamError, get_json
from engine.clients.pypi import project_url, summarise

CASES_DIR = Path(__file__).parent / "cases"

# Labels older than this make the benchmark untrustworthy; the runner says so.
MAX_LABEL_AGE_DAYS = 14

# One request at a time per host unless told otherwise: this is someone else's
# free infrastructure and we are reading 80 records, not racing.
DEFAULT_CONCURRENCY = 4


class LabelConflict(Exception):
    """The registry disagrees with the label. A human decides, not this script."""


async def fetch_pypi(client: httpx.AsyncClient, name: str) -> dict[str, Any]:
    """Registry facts for one package, or {'exists': False} on a 404."""
    body = await get_json(client, project_url(name), allow_404=True)
    return summarise(body)


async def verify_hallucinated(
    client: httpx.AsyncClient, case: dict[str, Any], stamp: str
) -> tuple[dict[str, Any], str | None]:
    """A hallucinated case must still 404. If it resolves, somebody registered it."""
    name = case["command"].split()[-1]
    facts = await fetch_pypi(client, name)
    if facts.get("exists"):
        # Do not relabel automatically: a name that appeared since the case was
        # written may be a benign project or may be the squat we predicted.
        return case, (
            f"{case['id']}: {name!r} now exists on PyPI — the label is stale. "
            "Review by hand: move it to typosquat/malicious or replace the name."
        )
    case["facts"] = {"exists": False}
    case["verified_at"] = stamp
    case["verified_source"] = True
    case["verified_by"] = "pypi_json_api"
    return case, None


async def verify_benign(
    client: httpx.AsyncClient, case: dict[str, Any], stamp: str
) -> tuple[dict[str, Any], str | None]:
    """Replace invented dates with what PyPI actually reports.

    The dates matter: the hand-written cases claim the last release of fastapi
    was 120 days ago, which is nowhere near true. Real dates will trip P6 on
    actively maintained packages and push some benign cases to REVIEW — that is
    the honest result, and the number the 7/30-day thresholds get tuned against.
    """
    name = case["command"].split()[-1].split("==")[0]
    facts = await fetch_pypi(client, name)
    if not facts.get("exists"):
        return case, (
            f"{case['id']}: {name!r} does not resolve on PyPI — a benign case "
            "should not 404. Check the spelling before the next run."
        )
    case["facts"] = facts
    case["verified_at"] = stamp
    case["verified_source"] = True
    case["verified_by"] = "pypi_json_api"
    return case, None


VERIFIERS = {
    "hallucinated": verify_hallucinated,
    "benign": verify_benign,
}


def load(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def save(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


async def run(labels: list[str], dry_run: bool, concurrency: int) -> int:
    stamp = datetime.now(UTC).isoformat()
    warnings: list[str] = []

    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
        semaphore = asyncio.Semaphore(concurrency)

        for label in labels:
            path = CASES_DIR / f"{label}.jsonl"
            if not path.exists():
                print(f"skip {label}: {path} not found")
                continue
            rows = load(path)
            verifier = VERIFIERS[label]

            if dry_run:
                print(f"{label}: would GET {len(rows)} records from pypi.org")
                continue

            async def one(case: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
                async with semaphore:
                    try:
                        return await verifier(client, case, stamp)
                    except UpstreamError as exc:
                        return case, f"{case['id']}: upstream error, label left as-is ({exc})"

            done = await asyncio.gather(*(one(case) for case in rows))
            save(path, [case for case, _ in done])
            warnings.extend(w for _, w in done if w)
            print(f"{label}: {len(rows)} cases verified, stamped {stamp}")

    if warnings:
        print(f"\n{len(warnings)} case(s) need a human:")
        for w in warnings:
            print(f"  - {w}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        nargs="+",
        default=sorted(VERIFIERS),
        choices=sorted(VERIFIERS),
        help="which case files to refresh",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would be fetched, fetch nothing"
    )
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    args = parser.parse_args()
    return asyncio.run(run(args.labels, args.dry_run, args.concurrency))


if __name__ == "__main__":
    raise SystemExit(main())
