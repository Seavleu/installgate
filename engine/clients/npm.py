"""npm registry. Existence, `time` map, maintainers, dist integrity."""

from __future__ import annotations

import hashlib
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


def _pin_digest(integrity: object, shasum: object, name: str, version: str) -> str:
    """Stable 64-hex pin from registry metadata. Not the tarball bytes (we never fetch them)."""
    raw = str(integrity or shasum or f"{name}@{version}")
    return hashlib.sha256(raw.encode()).hexdigest()


def summarise(body: dict[str, Any] | None, *, version: str | None = None) -> dict[str, Any]:
    if body is None:
        return {"exists": False}

    times: dict[str, Any] = body.get("time") or {}
    created = _parse(str(times.get("created") or ""))
    modified = _parse(str(times.get("modified") or ""))

    latest_version = ((body.get("dist-tags") or {}).get("latest")) or None
    versions: dict[str, Any] = body.get("versions") or {}
    pin_version = version if version and str(version) in versions else latest_version
    pin_meta = versions.get(str(pin_version)) or {}
    dist = pin_meta.get("dist") or {}
    integrity = dist.get("integrity")
    shasum = dist.get("shasum")
    name = str(body.get("name") or pin_meta.get("name") or "")

    maintainers = sorted(
        {
            str(m.get("name") or m.get("email"))
            for m in (body.get("maintainers") or [])
            if isinstance(m, dict) and (m.get("name") or m.get("email"))
        }
    )

    pin_sha = _pin_digest(integrity, shasum, name, str(pin_version)) if pin_version else None

    return {
        "exists": True,
        "latest_version": latest_version,
        "first_upload": created.isoformat() if created else None,
        "latest_upload": modified.isoformat() if modified else None,
        "maintainers": maintainers,
        "dist_integrity": integrity,
        "dist_shasum": shasum,
        "pin_version": pin_version,
        "pin_sha256": pin_sha,
        "latest_sha256": pin_sha,
        "release_count": len(versions),
    }


async def fetch(
    client: httpx.AsyncClient, target: TargetRef, cache: Cache | None = None
) -> dict[str, Any]:
    key = f"{target.name}@{target.version or 'latest'}"
    if cache is not None:
        cached = cache.get("npm", key)
        if cached is not None:
            return dict(cached)
    body = await get_json(client, project_url(target.name), allow_404=True)
    facts = summarise(body, version=target.version)
    if cache is not None:
        cache.set("npm", key, facts)
    return facts
