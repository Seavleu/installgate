"""PyPI JSON API. Existence, release dates, maintainers, file hashes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from contracts.contracts import TargetRef

from engine.cache import Cache
from engine.clients import get_json

BASE = "https://pypi.org/pypi"


def project_url(name: str) -> str:
    return f"{BASE}/{name}/json"


def _parse_upload_time(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def summarise(body: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten the PyPI payload into the facts the checks need."""
    if body is None:
        return {"exists": False}

    info = body.get("info") or {}
    releases: dict[str, list[dict[str, Any]]] = body.get("releases") or {}
    if not releases and body.get("urls"):
        # A release document (/pypi/{name}/{version}/json) has no `releases` map;
        # its files are under `urls` and describe that one version. Without this
        # the summary comes back with no dates and no hash, which reads as a
        # package nobody ever uploaded.
        releases = {str(info.get("version")): list(body["urls"])}

    upload_times: list[datetime] = []
    for files in releases.values():
        for f in files:
            parsed = _parse_upload_time(str(f.get("upload_time_iso_8601") or ""))
            if parsed:
                upload_times.append(parsed)

    latest_version = info.get("version")
    latest_files = releases.get(str(latest_version), []) if latest_version else []
    latest_upload = max(
        (
            t
            for t in (
                _parse_upload_time(str(f.get("upload_time_iso_8601") or "")) for f in latest_files
            )
            if t
        ),
        default=None,
    )
    sdist_sha = next(
        (
            str((f.get("digests") or {}).get("sha256"))
            for f in latest_files
            if (f.get("digests") or {}).get("sha256")
        ),
        None,
    )

    maintainers = sorted(
        {
            str(value)
            for key in ("author", "maintainer", "author_email", "maintainer_email")
            if (value := info.get(key))
        }
    )

    return {
        "exists": True,
        "latest_version": latest_version,
        "first_upload": min(upload_times).isoformat() if upload_times else None,
        "latest_upload": latest_upload.isoformat() if latest_upload else None,
        "maintainers": maintainers,
        "latest_sha256": sdist_sha,
        "release_count": len(releases),
    }


async def fetch(
    client: httpx.AsyncClient, target: TargetRef, cache: Cache | None = None
) -> dict[str, Any]:
    if cache is not None:
        cached = cache.get("pypi", target.name)
        if cached is not None:
            return dict(cached)
    body = await get_json(client, project_url(target.name), allow_404=True)
    facts = summarise(body)
    if cache is not None:
        cache.set("pypi", target.name, facts)
    return facts
