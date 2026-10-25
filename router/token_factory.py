"""Nebius Token Factory client (T02). Resolve model ids from GET /v1/models. Metadata only."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

ALLOWED_HOST = "api.tokenfactory.nebius.com"
DEFAULT_BASE = "https://api.tokenfactory.nebius.com/v1/"
TIMEOUT_S = 15.0
SMOKE_TIMEOUT_S = 30.0

_log = logging.getLogger("installgate.router")

_TIER_NEEDLES: dict[str, tuple[str, ...]] = {
    "nano": ("nemotron-3-nano", "nemotron-nano"),
    "super": ("nemotron-3-super", "nemotron-super"),
    "ultra": ("nemotron-3-ultra", "nemotron-ultra"),
}


class TokenFactoryError(RuntimeError):
    """Call failed. Callers must fail closed to REVIEW."""


@dataclass(frozen=True)
class ModelIds:
    nano: str | None
    super: str | None
    ultra: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {"nano": self.nano, "super": self.super, "ultra": self.ultra}


@dataclass(frozen=True)
class SmokeResult:
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    failed_closed: bool
    model_ids: ModelIds

    def as_log(self) -> dict[str, Any]:
        return {
            "stage": "smoke",
            "model_ids": self.model_ids.as_dict(),
            "model_id": self.model_id,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_ms": self.latency_ms,
            "failed_closed": self.failed_closed,
        }


def _base_url() -> str:
    raw = os.environ.get("NEBIUS_BASE_URL", DEFAULT_BASE).strip() or DEFAULT_BASE
    if not raw.endswith("/"):
        raw += "/"
    host = urlparse(raw).hostname or ""
    if host != ALLOWED_HOST:
        raise TokenFactoryError(f"host not on allowlist: {host!r} (need {ALLOWED_HOST})")
    return raw


def _headers() -> dict[str, str]:
    key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not key:
        raise TokenFactoryError("NEBIUS_API_KEY is missing")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _pick(catalog: list[str], tier: str) -> str | None:
    override = os.environ.get(f"MODEL_{tier.upper()}", "").strip()
    lowered = [item.casefold() for item in catalog]
    if override:
        if override.casefold() in lowered:
            return catalog[lowered.index(override.casefold())]
        return None
    needles = _TIER_NEEDLES[tier]
    for item in catalog:
        folded = item.casefold()
        if any(n in folded for n in needles):
            return item
    return None


async def resolve_model_ids(client: httpx.AsyncClient | None = None) -> ModelIds:
    """GET /v1/models. Missing tiers stay None (disabled). Catalog errors fail closed."""
    base = _base_url()
    own = client is None
    http = client or httpx.AsyncClient(timeout=TIMEOUT_S)
    try:
        response = await http.get(f"{base}models", headers=_headers())
        if response.status_code >= 400:
            raise TokenFactoryError(f"models list failed: HTTP {response.status_code}")
        payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise TokenFactoryError("models list missing data")
        catalog = [str(row["id"]) for row in rows if isinstance(row, dict) and "id" in row]
        return ModelIds(
            nano=_pick(catalog, "nano"),
            super=_pick(catalog, "super"),
            ultra=_pick(catalog, "ultra"),
        )
    except TokenFactoryError:
        raise
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise TokenFactoryError("models list failed") from exc
    finally:
        if own:
            await http.aclose()


def _message_text(choice: dict[str, Any]) -> str:
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    reasoning = message.get("reasoning_content")
    if isinstance(reasoning, str):
        return reasoning
    return ""


async def smoke(client: httpx.AsyncClient | None = None) -> SmokeResult:
    """One cheap Nano ping. Logs model ids, tokens, latency. Never logs the API key."""
    ids = await resolve_model_ids(client)
    model = ids.nano or ids.super
    if model is None:
        raise TokenFactoryError("no Nano or Super model id in catalog")
    base = _base_url()
    own = client is None
    http = client or httpx.AsyncClient(timeout=SMOKE_TIMEOUT_S)
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word pong."}],
        "max_tokens": 8,
        # Flattened OpenAI extra_body; Nano should not emit a thinking block.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    started = time.perf_counter()
    try:
        response = await http.post(f"{base}chat/completions", headers=_headers(), json=body)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise TokenFactoryError(f"smoke completion failed: HTTP {response.status_code}")
        payload = response.json()
        usage = payload.get("usage") or {}
        choices = payload.get("choices") or []
        if choices:
            _message_text(choices[0])
        result = SmokeResult(
            model_id=model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
            failed_closed=False,
            model_ids=ids,
        )
        _log.info(json.dumps(result.as_log(), separators=(",", ":")))
        return result
    except TokenFactoryError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise TokenFactoryError("smoke completion failed") from exc
    finally:
        if own:
            await http.aclose()
