"""PyPI JSON API. Existence, release dates, maintainers, file hashes."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

import httpx
from contracts.contracts import TargetRef
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.tags import Tag, sys_tags
from packaging.utils import InvalidWheelFilename, parse_wheel_filename
from packaging.version import InvalidVersion, Version

from engine.cache import Cache
from engine.clients import get_json

BASE = "https://pypi.org/pypi"


def project_url(name: str) -> str:
    return f"{BASE}/{name}/json"


def cache_key(name: str, python: tuple[int, int] | None = None) -> str:
    major, minor = python or sys.version_info[:2]
    return f"{name}:cp{major}{minor}"


def _parse_upload_time(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _python_ok(spec: object, python: str) -> bool:
    if not spec:
        return True
    try:
        return python in SpecifierSet(str(spec))
    except InvalidSpecifier:
        return False


def _usable_files(
    files: list[dict[str, Any]], python: str, tags: list[Tag]
) -> list[dict[str, Any]]:
    usable: list[dict[str, Any]] = []
    for item in files:
        if item.get("yanked"):
            continue
        if not _python_ok(item.get("requires_python"), python):
            continue
        usable.append(item)
    if not usable:
        return []
    if _file_sha(usable, tags) is None:
        return []
    return usable


def _file_sha(files: list[dict[str, Any]], tags: list[Tag]) -> str | None:
    wheels: list[tuple[frozenset[Tag], str]] = []
    sdist: str | None = None
    for item in files:
        digest = (item.get("digests") or {}).get("sha256")
        if not digest:
            continue
        name = str(item.get("filename") or "")
        if name.endswith(".whl"):
            try:
                _, _, _, wheel_tags = parse_wheel_filename(name)
            except InvalidWheelFilename:
                continue
            wheels.append((wheel_tags, str(digest)))
            continue
        if sdist is None:
            sdist = str(digest)
    for tag in tags:
        for wheel_tags, digest in wheels:
            if tag in wheel_tags:
                return digest
    return sdist


def _newest_installable(
    releases: dict[str, list[dict[str, Any]]], python: str, tags: list[Tag]
) -> tuple[str | None, list[dict[str, Any]]]:
    ranked: list[tuple[Version, str]] = []
    for version in releases:
        try:
            ranked.append((Version(version), version))
        except InvalidVersion:
            continue
    ranked.sort(reverse=True)
    for _, version in ranked:
        files = _usable_files(releases.get(version) or [], python, tags)
        if files:
            return version, files
    return None, []


def summarise(
    body: dict[str, Any] | None,
    *,
    python: tuple[int, int] | None = None,
    tags: list[Tag] | None = None,
) -> dict[str, Any]:
    """Flatten the PyPI payload into the facts the checks need.

    `latest_version` is what PyPI reports. `pin_version` is the newest release
    this interpreter can actually install (requires_python + a matching wheel
    or sdist). Unpinned checks pin `pin_version`, not a 3.12-only latest on 3.11.
    """
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
        for item in files:
            parsed = _parse_upload_time(str(item.get("upload_time_iso_8601") or ""))
            if parsed:
                upload_times.append(parsed)

    major, minor = python or sys.version_info[:2]
    python_s = f"{major}.{minor}"
    tag_list = tags if tags is not None else list(sys_tags())

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
    latest_sha = _file_sha(latest_files, tag_list) or next(
        (
            str((f.get("digests") or {}).get("sha256"))
            for f in latest_files
            if (f.get("digests") or {}).get("sha256")
        ),
        None,
    )

    pin_version, pin_files = _newest_installable(releases, python_s, tag_list)
    pin_sha = _file_sha(pin_files, tag_list) if pin_files else None

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
        "latest_sha256": latest_sha,
        "pin_version": pin_version,
        "pin_sha256": pin_sha,
        "release_count": len(releases),
    }


async def fetch(
    client: httpx.AsyncClient, target: TargetRef, cache: Cache | None = None
) -> dict[str, Any]:
    key = cache_key(target.name)
    if cache is not None:
        cached = cache.get("pypi", key)
        if cached is not None:
            return dict(cached)
    body = await get_json(client, project_url(target.name), allow_404=True)
    facts = summarise(body)
    if cache is not None:
        cache.set("pypi", key, facts)
    return facts
