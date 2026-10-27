"""npm registry. Existence, `time` map, maintainers, dist integrity."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from contracts.contracts import TargetRef

from engine.cache import Cache
from engine.clients import get_json

BASE = "https://registry.npmjs.org"


def project_url(name: str) -> str:
    # A scoped name (@scope/pkg) must have its slash encoded.
    return f"{BASE}/{quote(name, safe='@')}"


def _parse(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def summarise(body: dict[str, Any] | None) -> dict[str, Any]:
    if body is None:
        return {"exists": False}

    times: dict[str, Any] = body.get("time") or {}
    created = _parse(str(times.get("created") or ""))
    modified = _parse(str(times.get("modified") or ""))

    latest_version = ((body.get("dist-tags") or {}).get("latest")) or None
    versions: dict[str, Any] = body.get("versions") or {}
    latest_meta = versions.get(str(latest_version)) or {}
    integrity = (latest_meta.get("dist") or {}).get("integrity")
    shasum = (latest_meta.get("dist") or {}).get("shasum")

    maintainers = sorted(
        {
            str(m.get("name") or m.get("email"))
            for m in (body.get("maintainers") or [])
            if isinstance(m, dict) and (m.get("name") or m.get("email"))
        }
    )

    return {
        "exists": True,
        "latest_version": latest_version,
        "first_upload": created.isoformat() if created else None,
        "latest_upload": modified.isoformat() if modified else None,
        "maintainers": maintainers,
        "dist_integrity": integrity,
        "dist_shasum": shasum,
        "release_count": len(versions),
    }


async def fetch(
    client: httpx.AsyncClient, target: TargetRef, cache: Cache | None = None
) -> dict[str, Any]:
    if cache is not None:
        cached = cache.get("npm", target.name)
        if cached is not None:
            return dict(cached)
    body = await get_json(client, project_url(target.name), allow_404=True)
    facts = summarise(body)
    if cache is not None:
        cache.set("npm", target.name, facts)
    return facts
