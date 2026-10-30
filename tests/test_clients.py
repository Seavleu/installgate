"""Registry clients and cache, exercised through httpx.MockTransport (no network)."""

import asyncio
from pathlib import Path

import httpx
import pytest
from contracts.contracts import Ecosystem, TargetRef
from engine import cache as cache_module
from engine.cache import Cache
from engine.clients import UpstreamError, get_json, npm, pypi
from engine.stage1 import enrich_target
from packaging.tags import Tag


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


def _file(
    filename: str,
    sha: str,
    *,
    requires_python: str,
    uploaded: str = "2024-01-01T00:00:00Z",
) -> dict[str, object]:
    return {
        "filename": filename,
        "requires_python": requires_python,
        "yanked": False,
        "upload_time_iso_8601": uploaded,
        "digests": {"sha256": sha},
    }


def test_pypi_summarise_pins_a_wheel_this_interpreter_can_install() -> None:
    sha_312 = "a" * 64
    sha_311 = "b" * 64
    body = {
        "info": {"version": "2.5.4"},
        "releases": {
            "2.5.4": [
                _file(
                    "numpy-2.5.4-cp312-cp312-macosx_11_0_arm64.whl",
                    sha_312,
                    requires_python=">=3.12",
                    uploaded="2026-10-01T00:00:00Z",
                )
            ],
            "2.2.6": [
                _file(
                    "numpy-2.2.6-cp311-cp311-macosx_11_0_arm64.whl",
                    sha_311,
                    requires_python=">=3.10",
                    uploaded="2025-01-01T00:00:00Z",
                )
            ],
        },
    }
    tags = [Tag("cp311", "cp311", "macosx_11_0_arm64")]
    facts = pypi.summarise(body, python=(3, 11), tags=tags)
    assert facts["latest_version"] == "2.5.4"
    assert facts["pin_version"] == "2.2.6"
    assert facts["pin_sha256"] == sha_311
    py312 = pypi.summarise(body, python=(3, 12), tags=[Tag("cp312", "cp312", "macosx_11_0_arm64")])
    assert py312["pin_version"] == "2.5.4"
    assert py312["pin_sha256"] == sha_312


def test_enrich_unpinned_uses_the_compatible_pin() -> None:
    ref = TargetRef(ecosystem=Ecosystem.PYPI, name="numpy")
    pinned = enrich_target(
        ref,
        {
            "exists": True,
            "latest_version": "2.5.4",
            "latest_sha256": "a" * 64,
            "pin_version": "2.2.6",
            "pin_sha256": "b" * 64,
        },
    )
    assert pinned.version == "2.2.6"
    assert pinned.artifact_sha256 == "b" * 64


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


def test_npm_summarise_pins_the_requested_version() -> None:
    body = {
        "name": "lodash",
        "dist-tags": {"latest": "4.17.21"},
        "time": {"created": "2012-04-23T00:00:00.000Z", "modified": "2021-02-20T00:00:00.000Z"},
        "versions": {
            "4.17.21": {
                "name": "lodash",
                "dist": {"integrity": "sha512-abc", "shasum": "deadbeef"},
            }
        },
        "maintainers": [{"name": "jdalton"}],
    }
    facts = npm.summarise(body, version="4.17.21")
    assert facts["exists"] is True
    assert facts["pin_version"] == "4.17.21"
    assert facts["pin_sha256"] == facts["latest_sha256"]
    assert len(facts["pin_sha256"]) == 64
