"""T02: resolve Token Factory model ids; smoke logs tokens and latency. No live network."""

from __future__ import annotations

import json
import os

import httpx
import pytest
import respx
from router.token_factory import (
    ALLOWED_HOST,
    TokenFactoryError,
    resolve_model_ids,
    smoke,
)


def _model(model_id: str) -> dict[str, object]:
    return {"id": model_id, "object": "model", "created": 0, "owned_by": "nvidia"}


CATALOG = {
    "object": "list",
    "data": [
        _model("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
        _model("nvidia/nemotron-3-super-120b-a12b"),
        _model("nvidia/Nemotron-3-Ultra-550b-a55b"),
    ],
}
BASE = "https://api.tokenfactory.nebius.com/v1/"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.setenv("NEBIUS_BASE_URL", BASE)
    monkeypatch.delenv("MODEL_NANO", raising=False)
    monkeypatch.delenv("MODEL_SUPER", raising=False)
    monkeypatch.delenv("MODEL_ULTRA", raising=False)


@respx.mock
@pytest.mark.asyncio
async def test_resolve_model_ids_from_catalog() -> None:
    respx.get(f"{BASE}models").mock(return_value=httpx.Response(200, json=CATALOG))
    ids = await resolve_model_ids()
    assert ids.nano == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    assert ids.super == "nvidia/nemotron-3-super-120b-a12b"
    assert ids.ultra == "nvidia/Nemotron-3-Ultra-550b-a55b"


@respx.mock
@pytest.mark.asyncio
async def test_missing_tier_is_disabled() -> None:
    respx.get(f"{BASE}models").mock(
        return_value=httpx.Response(
            200,
            json={"object": "list", "data": [_model("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")]},
        )
    )
    ids = await resolve_model_ids()
    assert ids.nano is not None
    assert ids.super is None
    assert ids.ultra is None


@respx.mock
@pytest.mark.asyncio
async def test_env_override_must_exist_in_catalog() -> None:
    os.environ["MODEL_NANO"] = "nvidia/not-in-catalog"
    respx.get(f"{BASE}models").mock(return_value=httpx.Response(200, json=CATALOG))
    ids = await resolve_model_ids()
    assert ids.nano is None


@respx.mock
@pytest.mark.asyncio
async def test_catalog_error_fail_closed() -> None:
    respx.get(f"{BASE}models").mock(return_value=httpx.Response(500, text="nope"))
    with pytest.raises(TokenFactoryError):
        await resolve_model_ids()


@pytest.mark.asyncio
async def test_non_allowlisted_host_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEBIUS_BASE_URL", "https://evil.example/v1/")
    with pytest.raises(TokenFactoryError, match="allowlist"):
        await resolve_model_ids()


def _completion(model_id: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "ok"},
            }
        ],
        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
    }


@respx.mock
@pytest.mark.asyncio
async def test_smoke_logs_nano_and_super() -> None:
    nano = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    super_id = "nvidia/nemotron-3-super-120b-a12b"
    respx.get(f"{BASE}models").mock(return_value=httpx.Response(200, json=CATALOG))
    route = respx.post(f"{BASE}chat/completions").mock(
        return_value=httpx.Response(200, json=_completion(nano))
    )
    results = await smoke()
    assert [item.model_id for item in results] == [nano, super_id]
    sent = [json.loads(call.request.content)["model"] for call in route.calls]
    assert sent == [nano, super_id]
    for result in results:
        assert result.failed_closed is False
        assert result.prompt_tokens == 4
        assert result.completion_tokens == 2
        assert result.latency_ms >= 0
        log = result.as_log()
        assert log["stage"] == "smoke"
        assert log["model_ids"]["ultra"] == "nvidia/Nemotron-3-Ultra-550b-a55b"
        assert "test-key" not in str(log)
    assert ALLOWED_HOST in BASE


@respx.mock
@pytest.mark.asyncio
async def test_smoke_skips_missing_nano() -> None:
    super_id = "nvidia/nemotron-3-super-120b-a12b"
    respx.get(f"{BASE}models").mock(
        return_value=httpx.Response(
            200,
            json={"object": "list", "data": [_model(super_id)]},
        )
    )
    route = respx.post(f"{BASE}chat/completions").mock(
        return_value=httpx.Response(200, json=_completion(super_id))
    )
    results = await smoke()
    assert [item.model_id for item in results] == [super_id]
    assert len(route.calls) == 1
