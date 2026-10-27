"""Registry clients and cache, exercised through httpx.MockTransport (no network)."""

import asyncio
from pathlib import Path

import httpx
import pytest
from contracts.contracts import Ecosystem, TargetRef
from engine import cache as cache_module
from engine.cache import Cache
from engine.clients import UpstreamError, get_json, pypi


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


def test_host_outside_allowlist_is_refused_without_a_request() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    async def run() -> None:
        async with _client(httpx.MockTransport(handler)) as client:
            await get_json(client, "https://evil.example.com/pypi/requests/json")

    with pytest.raises(UpstreamError, match="not allowlisted"):
        asyncio.run(run())
    assert calls == []


def test_404_means_missing_when_allowed_and_error_otherwise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async def run(allow_404: bool) -> object:
        async with _client(httpx.MockTransport(handler)) as client:
            return await get_json(client, "https://pypi.org/pypi/nope/json", allow_404=allow_404)

    assert asyncio.run(run(True)) is None
    with pytest.raises(UpstreamError, match="404"):
        asyncio.run(run(False))


def test_timeout_becomes_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async def run() -> None:
        async with _client(httpx.MockTransport(handler)) as client:
            await get_json(client, "https://pypi.org/pypi/requests/json")

    with pytest.raises(UpstreamError, match="failed"):
        asyncio.run(run())


def test_cache_serves_fresh_entries_and_drops_expired_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = Cache(tmp_path / "c.sqlite")
    try:
        clock = [1000.0]
        monkeypatch.setattr(cache_module.time, "time", lambda: clock[0])
        cache.set("osv", "requests", {"x": 1})
        assert cache.get("osv", "requests") == {"x": 1}
        clock[0] += cache_module.TTL_SECONDS["osv"] + 1
        assert cache.get("osv", "requests") is None
    finally:
        cache.close()


def test_pypi_fetch_hits_the_network_once_then_uses_the_cache(tmp_path: Path) -> None:
    hits = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal hits
        hits += 1
        return httpx.Response(404)

    cache = Cache(tmp_path / "c.sqlite")
    ref = TargetRef(ecosystem=Ecosystem.PYPI, name="ghost-pkg-xyz")

    async def run() -> list[dict[str, object]]:
        async with _client(httpx.MockTransport(handler)) as client:
            return [await pypi.fetch(client, ref, cache), await pypi.fetch(client, ref, cache)]

    try:
        first, second = asyncio.run(run())
    finally:
        cache.close()
    assert first == second == {"exists": False}
    assert hits == 1
