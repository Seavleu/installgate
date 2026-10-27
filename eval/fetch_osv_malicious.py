"""Build the malicious case set from real OSV MAL- records. ONLINE — run by hand.

    uv run python -m eval.fetch_osv_malicious --dry-run   # list what it would fetch
    uv run python -m eval.fetch_osv_malicious --limit 50

Source: the ossf/malicious-packages repository, which publishes OSV records for
malicious packages as individual JSON files under osv/malicious/<ecosystem>/.
We ask the GitHub tree API for the list of paths, choose `--limit` of them, and
download only those files. The OSV bulk archives would also work but mean
pulling the entire corpus to keep fifty records.

What lands on disk is OSV metadata: an advisory id, a package name, dates and a
summary. No package artefact, no wheel, no tarball, no code from any malicious
package is fetched, stored or executed, here or anywhere else in InstallGate
(NFR-01).

Each case records where it came from: the repository, the commit the tree was
read at, the file path and the fetch date. A reader can re-derive any row.

About the registry facts in each case
-------------------------------------
Most packages in these advisories were removed by the registry after the report.
Checked live they return 404, so P1 (`not_found`) fires and P2 (`osv_malicious`)
never runs — the benchmark would report high recall while leaving the OSV path
untested. The script therefore writes two kinds of case:

  * `registry_state: "live"` — fetched from PyPI now. Usually absent, so P1.
  * `registry_state: "simulated_pre_removal"` — the same advisory with facts
    describing the package as it was before removal, so P2 carries the verdict.

The second kind is a simulation and is labelled as one in the case, in the
report and in `results.md`. It tests the OSV wiring; it is not evidence about
the world.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

CASES_DIR = Path(__file__).parent / "cases"
PROVENANCE_PATH = CASES_DIR / "malicious.provenance.json"

REPO = "ossf/malicious-packages"
BRANCH = "main"
TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"

# PyPI only: the npm typosquat reference set was cut from this milestone, so an
# npm case could not be judged by P4/P5 anyway. See results.md.
ECOSYSTEM_PREFIX = "osv/malicious/pypi/"

TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
HEADERS = {
    "User-Agent": "InstallGate/0.1 (benchmark label fetch; metadata only)",
    "Accept": "application/vnd.github+json",
}
DEFAULT_CONCURRENCY = 4
SHA_PLACEHOLDER = "b" * 64


async def list_record_paths(client: httpx.AsyncClient) -> tuple[list[str], str]:
    """Every MAL- record path under the PyPI folder, plus the tree sha we read."""
    response = await client.get(TREE_URL)
    response.raise_for_status()
    body = response.json()
    if body.get("truncated"):
        # Partial tree would make the selection unreproducible; say so loudly.
        raise RuntimeError(
            "GitHub returned a truncated tree. Narrow the request before trusting "
            "the selection, or the 50 records are not reproducible."
        )
    paths = sorted(
        item["path"]
        for item in body.get("tree", [])
        if item.get("type") == "blob"
        and item["path"].startswith(ECOSYSTEM_PREFIX)
        and item["path"].endswith(".json")
    )
    return paths, str(body.get("sha", "unknown"))


async def fetch_record(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    response = await client.get(f"{RAW_BASE}/{path}")
    response.raise_for_status()
    return dict(response.json())


def package_name(record: dict[str, Any]) -> str | None:
    for affected in record.get("affected") or []:
        package = (affected or {}).get("package") or {}
        if package.get("name"):
            return str(package["name"])
    return None


def to_case(
    index: int,
    record: dict[str, Any],
    path: str,
    tree_sha: str,
    stamp: str,
    simulate: bool,
) -> dict[str, Any] | None:
    name = package_name(record)
    mal_id = record.get("id")
    if not name or not mal_id or not str(mal_id).startswith("MAL-"):
        return None

    published = str(record.get("published") or record.get("modified") or "")
    if simulate:
        # A plausible pre-removal shape: the package existed, was days old, and
        # had one unknown maintainer. Dates are anchored to the advisory itself.
        anchor = _parse(published) or datetime.now(UTC)
        facts = {
            "exists": True,
            "latest_version": "0.0.1",
            "latest_sha256": SHA_PLACEHOLDER,
            "first_upload": (anchor - timedelta(days=3)).isoformat(),
            "latest_upload": (anchor - timedelta(days=3)).isoformat(),
            "maintainers": ["unknown"],
        }
        registry_state = "simulated_pre_removal"
    else:
        facts = {"exists": False}
        registry_state = "live_unverified"

    return {
        "id": f"malicious-{index:03d}",
        "label": "malicious",
        "ecosystem": "pypi",
        "command": f"pip install {name}",
        "expected_verdict": "BLOCK",
        "facts": facts,
        "osv": {"malicious": True, "mal_ids": [str(mal_id)]},
        "registry_state": registry_state,
        "verified_source": not simulate,
        "provenance": {
            "repo": REPO,
            "tree_sha": tree_sha,
            "path": path,
            "advisory_published": published,
            "fetched_at": stamp,
        },
        "notes": (
            "Registry facts simulate the package as it was before removal so that "
            "P2 (osv_malicious) is the rule under test rather than P1 (not_found)."
            if simulate
            else "Registry state not yet confirmed; run eval.verify_labels to fill facts."
        ),
    }


def _parse(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def select(paths: list[str], limit: int) -> list[str]:
    """Evenly spaced through the sorted list, so the sample is not one campaign
    from one week. Deterministic: same tree and same limit give the same rows."""
    if limit >= len(paths):
        return paths
    step = len(paths) / limit
    return [paths[int(i * step)] for i in range(limit)]


async def run(limit: int, simulate_share: float, dry_run: bool, concurrency: int) -> int:
    stamp = datetime.now(UTC).isoformat()

    if dry_run:
        # Touch nothing. This mode exists so the network calls can be reviewed
        # before any of them happen, so it must not make one to describe itself.
        print("no requests made. A real run would:")
        print(f"  1. GET {TREE_URL}")
        print(f"     -> list every *.json blob under {ECOSYSTEM_PREFIX}")
        print(f"  2. select {limit} of them, evenly spaced through the sorted list")
        print(f"  3. GET each selected file from {RAW_BASE}/<path>")
        print(f"     -> {limit} requests, OSV advisory JSON only, no package artefacts")
        print(f"  4. write eval/cases/malicious.jsonl and {PROVENANCE_PATH.name}")
        print(f"     -> {int(limit * simulate_share)} cases with simulated pre-removal facts")
        return 0

    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        paths, tree_sha = await list_record_paths(client)
        print(f"{len(paths)} MAL- records under {ECOSYSTEM_PREFIX} at tree {tree_sha[:12]}")
        chosen = select(paths, limit)

        semaphore = asyncio.Semaphore(concurrency)

        async def one(path: str) -> tuple[str, dict[str, Any] | None]:
            async with semaphore:
                try:
                    return path, await fetch_record(client, path)
                except httpx.HTTPError as exc:
                    print(f"  skip {path}: {exc}")
                    return path, None

        fetched = await asyncio.gather(*(one(path) for path in chosen))

    cases: list[dict[str, Any]] = []
    simulate_until = int(len(fetched) * simulate_share)
    for index, (path, record) in enumerate(fetched, start=1):
        if record is None:
            continue
        case = to_case(len(cases) + 1, record, path, tree_sha, stamp, index <= simulate_until)
        if case is not None:
            cases.append(case)

    if not cases:
        print("no usable records fetched; cases left untouched")
        return 1

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    with (CASES_DIR / "malicious.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for case in cases:
            fh.write(json.dumps(case, ensure_ascii=False) + "\n")

    PROVENANCE_PATH.write_text(
        json.dumps(
            {
                "source_repo": REPO,
                "source_url": f"https://github.com/{REPO}",
                "tree_sha": tree_sha,
                "ecosystem_prefix": ECOSYSTEM_PREFIX,
                "records_available": len(paths),
                "records_selected": len(cases),
                "simulated_pre_removal": simulate_until,
                "fetched_at": stamp,
                "note": "OSV advisory metadata only. No package artefacts were downloaded.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(cases)} cases ({simulate_until} simulated pre-removal)")
    print(f"provenance -> {PROVENANCE_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--simulate-share",
        type=float,
        default=0.5,
        help="fraction of cases given pre-removal facts so P2 is the rule under test",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    args = parser.parse_args()
    return asyncio.run(run(args.limit, args.simulate_share, args.dry_run, args.concurrency))


if __name__ == "__main__":
    raise SystemExit(main())
