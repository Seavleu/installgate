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


def summarise(body: dict[str, Any]) -> dict[str, Any]:
    vulns = body.get("vulns") or []
    mal_ids = sorted(
        {
            str(v["id"])
            for v in vulns
            if isinstance(v, dict) and str(v.get("id", "")).startswith("MAL-")
        }
    )
    other_ids = sorted(
        {
            str(v["id"])
            for v in vulns
            if isinstance(v, dict) and not str(v.get("id", "")).startswith("MAL-")
        }
    )
    return {
        "malicious": bool(mal_ids),
        "mal_ids": mal_ids,
        "other_ids": other_ids,
    }


async def fetch(
    client: httpx.AsyncClient, target: TargetRef, cache: Cache | None = None
) -> dict[str, Any]:
    ecosystem = OSV_ECOSYSTEM.get(target.ecosystem)
    if ecosystem is None:
        return {"malicious": False, "mal_ids": [], "other_ids": [], "queried": False}

    key = f"{ecosystem}:{target.name}:{target.version or ''}"
    if cache is not None:
        cached = cache.get("osv", key)
        if cached is not None:
            return dict(cached)

    payload: dict[str, Any] = {"package": {"name": target.name, "ecosystem": ecosystem}}
    if target.version:
        payload["version"] = target.version

    facts = summarise(await post_json(client, QUERY_URL, payload))
    facts["queried"] = True
    if cache is not None:
        cache.set("osv", key, facts)
    return facts
