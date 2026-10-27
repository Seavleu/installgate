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
  * touch a non-PyPI case. Hugging Face and container cases live in the same
    files and would otherwise be handed another ecosystem's facts;
  * touch a simulated malicious case. Those describe a package as it was before
    the registry removed it; checking them live would overwrite the very state
    they exist to preserve.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from contracts.contracts import TargetRef
from engine.clients import HEADERS, TIMEOUT, UpstreamError, get_json
from engine.clients.pypi import project_url, summarise
from engine.parsers import parse_pip

CASES_DIR = Path(__file__).parent / "cases"

# Labels older than this make the benchmark untrustworthy; the runner says so.
MAX_LABEL_AGE_DAYS = 14

# One request at a time per host unless told otherwise: this is someone else's
# free infrastructure and we are reading 80 records, not racing.
DEFAULT_CONCURRENCY = 4


class LabelConflict(Exception):
    """The registry disagrees with the label. A human decides, not this script."""


def target_of(case: dict[str, Any]) -> TargetRef:
    """Parse the case command with the real parser.

    Splitting on whitespace would hand `uvicorn[standard]==0.30.1` to the API
    verbatim and quietly 404. The parser already knows how to read a command.
    """
    return parse_pip(case["command"])[0]


def is_pypi(case: dict[str, Any]) -> bool:
    return case.get("ecosystem") == "pypi"


async def fetch_pypi(
    client: httpx.AsyncClient, name: str, version: str | None = None
) -> dict[str, Any]:
    """Registry facts for one package, or {'exists': False} on a 404.

    A pinned case asks for that exact release: `/pypi/{name}/{version}/json`.
    Reading the project-level document instead would stamp the case with the
    dates and hash of whatever shipped most recently, which is not the artefact
    the case pins.
    """
    url = (
        f"{project_url(name).removesuffix('/json')}/{version}/json"
        if version
        else project_url(name)
    )
    body = await get_json(client, url, allow_404=True)
    return summarise(body)


async def verify_hallucinated(
    client: httpx.AsyncClient, case: dict[str, Any], stamp: str
) -> tuple[dict[str, Any], str | None]:
    """A hallucinated case must still 404. If it resolves, somebody registered it."""
    name = target_of(case).name
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
    target = target_of(case)
    facts = await fetch_pypi(client, target.name, target.version)
    if not facts.get("exists"):
        return case, (
            f"{case['id']}: {target.name!r}"
            + (f" at {target.version}" if target.version else "")
            + " does not resolve on PyPI — a benign case should not 404. "
            "Check the spelling or the pinned version before the next run."
        )
    case["facts"] = facts
    case["verified_at"] = stamp
    case["verified_source"] = True
    case["verified_by"] = "pypi_json_api"
    return case, None


async def verify_malicious(
    client: httpx.AsyncClient, case: dict[str, Any], stamp: str
) -> tuple[dict[str, Any], str | None]:
    """Confirm the live malicious cases really are gone from the registry.

    Only `registry_state == "live_unverified"` is touched. A simulated case
    deliberately describes the package before removal so that P2 is the rule
    under test; overwriting it with a 404 would silently turn it back into a P1
    case and leave the OSV path untested again.

    A live case that still resolves is not an error — the package may simply not
    have been pulled yet. It is reported, because such a case tests P2 rather
    than P1 and the report splits recall along exactly that line.
    """
    if case.get("registry_state") != "live_unverified":
        return case, None

    target = target_of(case)
    facts = await fetch_pypi(client, target.name)
    case["facts"] = facts
    case["verified_at"] = stamp
    case["verified_source"] = True
    case["verified_by"] = "pypi_json_api"

    if facts.get("exists"):
        case["registry_state"] = "live_present"
        return case, (
            f"{case['id']}: {target.name!r} is still on PyPI. The case now tests "
            "P2 (osv_malicious) rather than P1 (not_found); the report counts it "
            "in the live group."
        )
    case["registry_state"] = "live_absent"
    return case, None


VERIFIERS = {
    "hallucinated": verify_hallucinated,
    "benign": verify_benign,
    "malicious": verify_malicious,
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
            # Only PyPI cases: a Hugging Face repo id or a container tag sent to
            # the PyPI API would 404 and the case would be stamped with the facts
            # of a package that does not exist.
            targets = [r for r in rows if is_pypi(r)]
            if label == "malicious":
                targets = [r for r in targets if r.get("registry_state") == "live_unverified"]
            skipped = len(rows) - len(targets)

            if dry_run:
                print(
                    f"{label}: would GET {len(targets)} record(s) from pypi.org"
                    + (f", skipping {skipped} non-PyPI or simulated" if skipped else "")
                )
                continue

            async def one(case: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
                async with semaphore:
                    try:
                        return await verifier(client, case, stamp)
                    except UpstreamError as exc:
                        return case, f"{case['id']}: upstream error, label left as-is ({exc})"

            done = await asyncio.gather(*(one(case) for case in targets))
            updated = {id(case): case for case, _ in done}
            save(path, [updated.get(id(row), row) for row in rows])
            warnings.extend(w for _, w in done if w)
            print(
                f"{label}: {len(targets)} case(s) verified, stamped {stamp}"
                + (f"; {skipped} left untouched" if skipped else "")
            )

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
