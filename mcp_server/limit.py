"""Per-visitor limit for POST /check (T14). A minute window, in memory."""

from __future__ import annotations

import os
import time

from starlette.requests import Request


class Limiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    def reset(self) -> None:
        self._hits.clear()

    def allow(self, key: str, *, limit: int, now: float | None = None) -> bool:
        if limit <= 0:
            return True
        moment = time.monotonic() if now is None else now
        window = [hit for hit in self._hits.get(key, []) if moment - hit < 60]
        if len(window) >= limit:
            self._hits[key] = window
            return False
        window.append(moment)
        self._hits[key] = window
        return True


limiter = Limiter()


def limit_per_minute() -> int:
    raw = os.environ.get("RATE_LIMIT_PER_MINUTE", "30")
    try:
        value = int(raw)
    except ValueError:
        return 30
    return value


def trust_proxy() -> bool:
    return os.environ.get("RATE_LIMIT_TRUST_PROXY", "").strip().lower() in {"1", "true", "yes"}


def client_key(request: Request) -> str:
    if trust_proxy():
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client is None:
        return "unknown"
    return request.client.host
