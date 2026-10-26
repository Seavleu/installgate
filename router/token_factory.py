"""Nebius Token Factory client (T02). Resolve model ids from GET /v1/models. Metadata only."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, TypeVar, cast
from urllib.parse import urlparse

import httpx
from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)
from openai.types.chat import ChatCompletionMessage
from pydantic import BaseModel, ValidationError

ALLOWED_HOST = "api.tokenfactory.nebius.com"
DEFAULT_BASE = "https://api.tokenfactory.nebius.com/v1/"
TIMEOUT_S = 15.0
SMOKE_TIMEOUT_S = 30.0

_log = logging.getLogger("installgate.router")
TModel = TypeVar("TModel", bound=BaseModel)

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


def _api_key() -> str:
    key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not key:
        raise TokenFactoryError("NEBIUS_API_KEY is missing")
    return key


def _openai(*, timeout: float) -> AsyncOpenAI:
    """OpenAI SDK pointed at Token Factory. Transport stays httpx so the host allowlist holds."""
    # The SDK types this as its vendored client; the runtime also accepts httpx.AsyncClient.
    http = cast(Any, httpx.AsyncClient(timeout=timeout))
    return AsyncOpenAI(
        base_url=_base_url(),
        api_key=_api_key(),
        timeout=timeout,
        max_retries=0,
        http_client=http,
    )


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


async def resolve_model_ids(client: AsyncOpenAI | None = None) -> ModelIds:
    """GET /v1/models. Missing tiers stay None (disabled). Catalog errors fail closed."""
    own = client is None
    api = client or _openai(timeout=TIMEOUT_S)
    try:
        page = await api.models.list()
        catalog = [item.id for item in page.data]
        return ModelIds(
            nano=_pick(catalog, "nano"),
            super=_pick(catalog, "super"),
            ultra=_pick(catalog, "ultra"),
        )
    except TokenFactoryError:
        raise
    except APIStatusError as exc:
        raise TokenFactoryError(f"models list failed: HTTP {exc.status_code}") from exc
    except (APIConnectionError, APITimeoutError, APIResponseValidationError) as exc:
        raise TokenFactoryError("models list failed") from exc
    finally:
        if own:
            await api.close()


@dataclass(frozen=True)
class StructuredCompletion:
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    schema_valid: bool
    retries: int


async def complete_structured(
    api: AsyncOpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    schema: type[TModel],
    extra_body: dict[str, Any] | None = None,
) -> tuple[TModel, StructuredCompletion]:
    """One JSON-schema completion. A bad parse is retried once. HTTP errors fail closed.

    shortcut: a rejected first parse is not its own RouteCall. Upgrade if the receipt must
    count tokens from the failed attempt.
    """
    schema_valid = True
    for attempt in (0, 1):
        started = time.perf_counter()
        try:
            response = await api.chat.completions.create(
                model=model,
                messages=cast(Any, messages),
                response_format=cast(
                    Any,
                    {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema.__name__,
                            "schema": schema.model_json_schema(),
                            "strict": False,
                        },
                    },
                ),
                extra_body=extra_body,
            )
        except APIStatusError as exc:
            raise TokenFactoryError(f"completion failed: HTTP {exc.status_code}") from exc
        except (APIConnectionError, APITimeoutError, APIResponseValidationError) as exc:
            raise TokenFactoryError("completion failed") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = response.usage
        raw = _message_text(response.choices[0].message) if response.choices else ""
        try:
            parsed = schema.model_validate_json(raw)
        except ValidationError:
            schema_valid = False
            if attempt == 0:
                continue
            raise TokenFactoryError("structured output invalid") from None
        return parsed, StructuredCompletion(
            prompt_tokens=int(usage.prompt_tokens) if usage else 0,
            completion_tokens=int(usage.completion_tokens) if usage else 0,
            latency_ms=latency_ms,
            schema_valid=schema_valid,
            retries=attempt,
        )
    raise TokenFactoryError("structured output invalid")


def _message_text(message: ChatCompletionMessage) -> str:
    content = message.content
    if isinstance(content, str) and content.strip():
        return content
    extra = message.model_extra or {}
    reasoning = extra.get("reasoning_content")
    if isinstance(reasoning, str):
        return reasoning
    return ""


async def smoke(client: AsyncOpenAI | None = None) -> list[SmokeResult]:
    """Cheap Nano and Super pings. Logs model ids, tokens, latency. Never logs the API key.

    A tier missing from the catalog is skipped. Neither tier present fails closed.
    Ultra is not pinged here.
    """
    own = client is None
    api = client or _openai(timeout=SMOKE_TIMEOUT_S)
    try:
        ids = await resolve_model_ids(api)
        models = [model for model in (ids.nano, ids.super) if model]
        if not models:
            raise TokenFactoryError("no Nano or Super model id in catalog")
        results: list[SmokeResult] = []
        for model in models:
            started = time.perf_counter()
            response = await api.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with the single word pong."}],
                max_tokens=8,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.choices:
                _message_text(response.choices[0].message)
            usage = response.usage
            result = SmokeResult(
                model_id=model,
                prompt_tokens=int(usage.prompt_tokens) if usage else 0,
                completion_tokens=int(usage.completion_tokens) if usage else 0,
                latency_ms=latency_ms,
                failed_closed=False,
                model_ids=ids,
            )
            _log.info(json.dumps(result.as_log(), separators=(",", ":")))
            results.append(result)
        return results
    except TokenFactoryError:
        raise
    except APIStatusError as exc:
        raise TokenFactoryError(f"smoke completion failed: HTTP {exc.status_code}") from exc
    except (APIConnectionError, APITimeoutError, APIResponseValidationError) as exc:
        raise TokenFactoryError("smoke completion failed") from exc
    finally:
        if own:
            await api.close()
