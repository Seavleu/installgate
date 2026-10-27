"""Build the malicious case set from real OSV MAL- records. ONLINE — run by hand.

    uv run python -m eval.fetch_osv_malicious --dry-run   # list what it would fetch
    uv run python -m eval.fetch_osv_malicious --limit 50

Source: the ossf/malicious-packages repository, which publishes OSV records for
malicious packages as individual JSON files under osv/malicious/<ecosystem>/.

The listing walks down to that one directory rather than asking for the whole
repository recursively: the full tree is large enough that GitHub truncates it,
and a truncated listing makes the selection unreproducible. We resolve the
branch to a commit sha, descend sha by sha to `osv/malicious/pypi`, and read
only that subtree. If even that comes back truncated we fall back to listing the
per-package directories one level at a time.

Everything is anchored to the commit sha, including the raw file URLs, so a rerun
against the same sha fetches byte-identical records even after the branch moves.

Rate limits: the unauthenticated GitHub API allows 60 requests an hour. The walk
costs four calls plus one per package directory in the fallback path; the record
downloads go to raw.githubusercontent.com, which is not the API and does not
count. The script reads the remaining quota from the response headers and stops
before exhausting it. Set GITHUB_TOKEN in the environment to raise the ceiling.

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
untested. The script therefore writes two kinds of case, interleaved so neither
kind clusters in one stretch of the advisory list:

  * `registry_state: "live_unverified"` — this script makes no PyPI call at all.
    The case is written with `exists: false` as a presumption and has to be
    confirmed by `eval.verify_labels`, which sets `live_absent` or `live_present`.
  * `registry_state: "simulated_pre_removal"` — the same advisory with facts
    describing the package as it was before removal, so P2 carries the verdict.
    `verify_labels` leaves these alone; checking them live would overwrite the
    very state they exist to preserve.

The second kind is a simulation and is labelled as one in the case, in the
report and in `results.md`. It tests the OSV wiring; it is not evidence about
the world, and the report never averages the two groups into one recall figure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from contracts.contracts import Ecosystem
from engine.checks import normalize_name

CASES_DIR = Path(__file__).parent / "cases"
PROVENANCE_PATH = CASES_DIR / "malicious.provenance.json"

REPO = "ossf/malicious-packages"
BRANCH = "main"
API = f"https://api.github.com/repos/{REPO}"

# PyPI only: the npm typosquat reference set was cut from this milestone, so an
# npm case could not be judged by P4/P5 anyway. See results.md.
RECORD_DIR = ("osv", "malicious", "pypi")

TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
DEFAULT_CONCURRENCY = 4
SHA_PLACEHOLDER = "b" * 64

# Leave room so a run never consumes the caller's last API calls.
RATE_LIMIT_RESERVE = 5


def build_headers() -> dict[str, str]:
    headers = {
        "User-Agent": "InstallGate/0.1 (benchmark label fetch; metadata only)",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def remaining_quota(response: httpx.Response) -> int | None:
    raw = response.headers.get("X-RateLimit-Remaining")
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


class RateLimited(RuntimeError):
    """Not enough API calls left to finish the walk without exhausting the quota."""


async def api_get(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(url)
    if response.status_code == 403 and remaining_quota(response) == 0:
        reset = response.headers.get("X-RateLimit-Reset", "unknown")
        raise RateLimited(
            f"GitHub API quota exhausted (resets at epoch {reset}). "
            "Set GITHUB_TOKEN to raise the unauthenticated limit of 60/hour."
        )
    response.raise_for_status()
    left = remaining_quota(response)
    if left is not None and left <= RATE_LIMIT_RESERVE:
        raise RateLimited(
            f"only {left} GitHub API calls left; stopping rather than consuming "
            "the last of the quota. Set GITHUB_TOKEN or wait for the reset."
        )
    return dict(response.json())


async def resolve_commit(client: httpx.AsyncClient) -> str:
    """Pin the branch to a commit sha, so tree and raw URLs agree with each other."""
    body = await api_get(client, f"{API}/commits/{BRANCH}")
    return str(body["sha"])


async def descend(client: httpx.AsyncClient, commit_sha: str) -> str:
    """Walk osv -> malicious -> pypi by sha and return that directory's tree sha.

    Four small requests instead of one recursive listing of the whole repository,
    which GitHub truncates.
    """
    body = await api_get(client, f"{API}/git/trees/{commit_sha}")
    sha = str(body["tree"] and commit_sha)
    for name in RECORD_DIR:
        entry = next(
            (
                item
                for item in body.get("tree", [])
                if item.get("path") == name and item.get("type") == "tree"
            ),
            None,
        )
        if entry is None:
            raise RuntimeError(f"{'/'.join(RECORD_DIR)} not found: no {name!r} at this level")
        sha = str(entry["sha"])
        body = await api_get(client, f"{API}/git/trees/{sha}")
    return sha


async def list_record_paths(client: httpx.AsyncClient, dir_sha: str) -> list[str]:
    """Record paths under the PyPI directory, relative to it.

    Tries one recursive listing of just that directory. If GitHub still marks it
    truncated, falls back to listing each package directory separately — more
    requests, but a complete and therefore reproducible list.
    """
    body = await api_get(client, f"{API}/git/trees/{dir_sha}?recursive=1")
    if not body.get("truncated"):
        return sorted(
            str(item["path"])
            for item in body.get("tree", [])
            if item.get("type") == "blob" and str(item["path"]).endswith(".json")
        )

    print("  subtree truncated; listing package directories one at a time")
    top = await api_get(client, f"{API}/git/trees/{dir_sha}")
    paths: list[str] = []
    for entry in top.get("tree", []):
        if entry.get("type") == "blob" and str(entry["path"]).endswith(".json"):
            paths.append(str(entry["path"]))
        elif entry.get("type") == "tree":
            sub = await api_get(client, f"{API}/git/trees/{entry['sha']}")
            paths.extend(
                f"{entry['path']}/{item['path']}"
                for item in sub.get("tree", [])
                if item.get("type") == "blob" and str(item["path"]).endswith(".json")
            )
    return sorted(paths)


def raw_url(commit_sha: str, path: str) -> str:
    """Anchored to the commit, not the branch: the branch moves, the sha does not."""
    return f"https://raw.githubusercontent.com/{REPO}/{commit_sha}/{'/'.join(RECORD_DIR)}/{path}"


async def fetch_record(client: httpx.AsyncClient, commit_sha: str, path: str) -> dict[str, Any]:
    response = await client.get(raw_url(commit_sha, path))
    response.raise_for_status()
    return dict(response.json())


def package_name(record: dict[str, Any]) -> str | None:
    for affected in record.get("affected") or []:
        package = (affected or {}).get("package") or {}
        if package.get("name"):
            return str(package["name"])
    return None


def is_withdrawn(record: dict[str, Any]) -> bool:
    """A withdrawn advisory was retracted. Treating it as ground truth would
    measure recall against a claim its own publisher took back."""
    return bool(record.get("withdrawn"))


def to_case(
    index: int,
    record: dict[str, Any],
    path: str,
    commit_sha: str,
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
        # The advisory is real either way; these registry facts are not. A
        # simulated case invents them outright, and a live case only presumes
        # the package is gone. eval.verify_labels sets this to true for the
        # live ones once it has actually asked PyPI.
        "verified_source": False,
        "provenance": {
            "repo": REPO,
            "commit_sha": commit_sha,
            "path": f"{'/'.join(RECORD_DIR)}/{path}",
            "url": raw_url(commit_sha, path),
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


async def run(
    limit: int, simulate_share: float, dry_run: bool, concurrency: int, margin: float
) -> int:
    stamp = datetime.now(UTC).isoformat()
    # Records get dropped: withdrawn advisories, duplicate package names, the
    # occasional malformed file. Fetch extra so a run still yields `limit` rows.
    attempt = min(int(limit * margin), 60)

    if dry_run:
        # Touch nothing. This mode exists so the network calls can be reviewed
        # before any of them happen, so it must not make one to describe itself.
        directory = "/".join(RECORD_DIR)
        token = "set" if os.environ.get("GITHUB_TOKEN") else "not set"
        print(f"no requests made. GITHUB_TOKEN is {token}. A real run would:")
        print(f"  1. GET {API}/commits/{BRANCH}            -> pin the branch to a commit sha")
        print(f"  2. GET {API}/git/trees/<sha> x3          -> descend to {directory}")
        print("  3. GET .../git/trees/<dir sha>?recursive=1 -> list the records")
        print("     (if truncated: one more call per package directory)")
        ceiling = "5000" if token == "set" else "60"
        print(f"     ~4-5 GitHub API calls total, against a limit of {ceiling}/hour")
        print(f"  4. select {attempt} paths evenly spaced through the sorted list")
        print(f"     ({limit} wanted, {margin:.1f}x margin for withdrawn and duplicate records)")
        print("  5. GET each from raw.githubusercontent.com/<repo>/<commit sha>/...")
        print(f"     -> {attempt} requests, not API calls, no quota consumed")
        print("     -> OSV advisory JSON only; no wheel, sdist or package artefact")
        print(f"  6. write eval/cases/malicious.jsonl and {PROVENANCE_PATH.name}")
        print(f"     -> every other case simulated pre-removal (~{simulate_share:.0%})")
        print("     -> live cases marked live_unverified for eval.verify_labels to confirm")
        return 0

    headers = build_headers()
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers, follow_redirects=True) as client:
        commit_sha = await resolve_commit(client)
        print(f"{REPO}@{BRANCH} is commit {commit_sha[:12]}")
        dir_sha = await descend(client, commit_sha)
        paths = await list_record_paths(client, dir_sha)
        print(f"{len(paths)} record files under {'/'.join(RECORD_DIR)}")

        chosen = select(paths, attempt)
        semaphore = asyncio.Semaphore(concurrency)

        async def one(path: str) -> tuple[str, dict[str, Any] | None]:
            async with semaphore:
                try:
                    return path, await fetch_record(client, commit_sha, path)
                except (httpx.HTTPError, ValueError) as exc:
                    print(f"  skip {path}: {exc}")
                    return path, None

        fetched = await asyncio.gather(*(one(path) for path in chosen))

    usable: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    withdrawn = duplicates = unusable = 0
    for path, record in fetched:
        if record is None:
            unusable += 1
            continue
        if is_withdrawn(record):
            withdrawn += 1
            continue
        name = package_name(record)
        if not name:
            unusable += 1
            continue
        key = normalize_name(name, Ecosystem.PYPI)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        usable.append((path, record))
        if len(usable) >= limit:
            break

    # Interleave rather than simulating the first half: the paths are sorted, so
    # a contiguous block would put every simulated case in one alphabetical
    # stretch, which tends to mean one campaign.
    cases: list[dict[str, Any]] = []
    stride = round(1 / simulate_share) if 0 < simulate_share <= 1 else 0
    for position, (path, record) in enumerate(usable):
        simulate = bool(stride) and position % stride == 0
        case = to_case(len(cases) + 1, record, path, commit_sha, stamp, simulate)
        if case is not None:
            cases.append(case)

    if not cases:
        print("no usable records fetched; cases left untouched")
        return 1

    simulated = sum(1 for c in cases if c["registry_state"] == "simulated_pre_removal")

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    with (CASES_DIR / "malicious.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for case in cases:
            fh.write(json.dumps(case, ensure_ascii=False) + "\n")

    PROVENANCE_PATH.write_text(
        json.dumps(
            {
                "source_repo": REPO,
                "source_url": f"https://github.com/{REPO}",
                "branch": BRANCH,
                "commit_sha": commit_sha,
                "record_dir": "/".join(RECORD_DIR),
                "records_available": len(paths),
                "records_attempted": len(chosen),
                "records_written": len(cases),
                "simulated_pre_removal": simulated,
                "live_unverified": len(cases) - simulated,
                "dropped": {
                    "withdrawn": withdrawn,
                    "duplicate_package": duplicates,
                    "unreadable": unusable,
                },
                "fetched_at": stamp,
                "note": "OSV advisory metadata only. No package artefacts were downloaded.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {len(cases)} cases: {simulated} simulated pre-removal, "
        f"{len(cases) - simulated} live_unverified"
    )
    if withdrawn or duplicates or unusable:
        print(f"dropped {withdrawn} withdrawn, {duplicates} duplicate names, {unusable} unreadable")
    if len(cases) < limit:
        print(f"WARNING: wanted {limit} cases, got {len(cases)}. Raise --margin and rerun.")
    print(f"provenance -> {PROVENANCE_PATH}")
    print("next: uv run python -m eval.verify_labels --labels malicious")
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
    parser.add_argument(
        "--margin",
        type=float,
        default=1.2,
        help="fetch this multiple of --limit to absorb withdrawn and duplicate records",
    )
    args = parser.parse_args()
    return asyncio.run(
        run(args.limit, args.simulate_share, args.dry_run, args.concurrency, args.margin)
    )


if __name__ == "__main__":
    raise SystemExit(main())
