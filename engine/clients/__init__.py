"""Read-only metadata clients. Allowlisted hosts, timeouts, no code execution."""

from __future__ import annotations

from typing import Any

import httpx

ALLOWED_HOSTS = frozenset(
    {
        "pypi.org",
        "registry.npmjs.org",
        "api.osv.dev",
        "huggingface.co",
    }
)

TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)
HEADERS = {"User-Agent": "InstallGate/0.1 (metadata-only pre-install check)"}


class UpstreamError(RuntimeError):
    """A registry call failed. The caller must fail closed to REVIEW."""


def _assert_allowed(url: str) -> None:
    host = httpx.URL(url).host
    if host not in ALLOWED_HOSTS:
        raise UpstreamError(f"host not allowlisted: {host}")


async def get_json(
    client: httpx.AsyncClient, url: str, *, allow_404: bool = False
) -> dict[str, Any] | None:
    """GET and parse JSON. Returns None on 404 when allow_404 (used for existence checks)."""
    _assert_allowed(url)
    try:
        response = await client.get(url, timeout=TIMEOUT, headers=HEADERS)
    except httpx.HTTPError as exc:
        raise UpstreamError(f"GET {url} failed: {exc}") from exc
    if response.status_code == 404 and allow_404:
        return None
    if response.status_code >= 400:
        raise UpstreamError(f"GET {url} returned {response.status_code}")
    try:
        body: dict[str, Any] = response.json()
    except ValueError as exc:
        raise UpstreamError(f"GET {url} returned non-JSON") from exc
    return body


async def post_json(client: httpx.AsyncClient, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    _assert_allowed(url)
    try:
        response = await client.post(url, json=payload, timeout=TIMEOUT, headers=HEADERS)
    except httpx.HTTPError as exc:
        raise UpstreamError(f"POST {url} failed: {exc}") from exc
    if response.status_code >= 400:
        raise UpstreamError(f"POST {url} returned {response.status_code}")
    try:
        body: dict[str, Any] = response.json()
    except ValueError as exc:
        raise UpstreamError(f"POST {url} returned non-JSON") from exc
    return body
