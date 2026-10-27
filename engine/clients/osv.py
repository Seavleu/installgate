"""OSV.dev query. Only MAL- records make a package malicious."""

from __future__ import annotations

from typing import Any

import httpx
from contracts.contracts import Ecosystem, TargetRef

from engine.cache import Cache
from engine.clients import post_json

QUERY_URL = "https://api.osv.dev/v1/query"

OSV_ECOSYSTEM = {
    Ecosystem.PYPI: "PyPI",
    Ecosystem.NPM: "npm",
}


def affected_spec(record: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    """What an advisory says about *which versions* it covers.

    A MAL- record usually lists exact versions. Some cover the whole project and
    name none. The difference decides whether a clean release of a package that
    was once compromised may still be installed, so it has to survive into the
    evidence rather than collapsing to a boolean.
    """
    versions: list[str] = []
    ranges: list[dict[str, Any]] = []
    for affected in record.get("affected") or []:
        package = (affected or {}).get("package") or {}
        if name and package.get("name") and str(package["name"]).lower() != name.lower():
            continue
        versions.extend(str(v) for v in (affected.get("versions") or []))
        ranges.extend(r for r in (affected.get("ranges") or []) if isinstance(r, dict))

    return {
        "id": str(record.get("id", "")),
        "versions": sorted(set(versions)),
        "ranges": ranges,
        # No version information at all means the project as a whole is the
        # finding: every release is covered.
        "whole_package": not versions and not ranges,
    }


def summarise(body: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    vulns = [v for v in (body.get("vulns") or []) if isinstance(v, dict)]
    mal = [v for v in vulns if str(v.get("id", "")).startswith("MAL-")]
    other_ids = sorted({str(v["id"]) for v in vulns if not str(v.get("id", "")).startswith("MAL-")})
    records = [affected_spec(v, name) for v in mal]
    return {
        # True when a MAL- record exists for the *name*. Whether it covers the
        # version in hand is a separate question, answered by `mal_records`.
        "malicious": bool(mal),
        "mal_ids": sorted({r["id"] for r in records}),
        "mal_records": records,
        "other_ids": other_ids,
    }


async def fetch(
    client: httpx.AsyncClient, target: TargetRef, cache: Cache | None = None
) -> dict[str, Any]:
    ecosystem = OSV_ECOSYSTEM.get(target.ecosystem)
    if ecosystem is None:
        return {
            "malicious": False,
            "mal_ids": [],
            "mal_records": [],
            "other_ids": [],
            "queried": False,
        }

    # Always query by name, never by version. Asking OSV to filter would hide
    # which versions a record covers, and the check needs that to tell a
    # compromised release from a clean one of the same project.
    key = f"{ecosystem}:{target.name}"
    if cache is not None:
        cached = cache.get("osv", key)
        if cached is not None:
            return dict(cached)

    payload: dict[str, Any] = {"package": {"name": target.name, "ecosystem": ecosystem}}

    facts = summarise(await post_json(client, QUERY_URL, payload), name=target.name)
    facts["queried"] = True
    if cache is not None:
        cache.set("osv", key, facts)
    return facts
