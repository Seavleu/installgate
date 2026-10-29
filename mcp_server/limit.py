"""Per-visitor limit for POST /check (T14). A minute window, in memory."""

from __future__ import annotations

import os
import time

from starlette.requests import Request

MAX_KEYS = 10_000


class Limiter:
    def __init__(self, max_keys: int = MAX_KEYS) -> None:
        self._hits: dict[str, list[float]] = {}
        self._max_keys = max_keys

    def reset(self) -> None:
        self._hits.clear()

    def __len__(self) -> int:
        return len(self._hits)

    def _prune(self, moment: float) -> None:
        for key in [k for k, hits in self._hits.items() if not hits or moment - hits[-1] >= 60]:
            del self._hits[key]
        # Still full of live keys: drop the least recently seen.
        overflow = len(self._hits) - self._max_keys + 1
        if overflow > 0:
            oldest = sorted(self._hits, key=lambda k: self._hits[k][-1])[:overflow]
            for key in oldest:
                del self._hits[key]

    def allow(self, key: str, *, limit: int, now: float | None = None) -> bool:
        if limit <= 0:
            return True
        moment = time.monotonic() if now is None else now
        if key not in self._hits and len(self._hits) >= self._max_keys:
            self._prune(moment)
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
    # Only the rightmost entry was written by our proxy. Earlier entries come from the client.
    if trust_proxy():
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.split(",")[-1].strip()
        if last:
            return last
    if request.client is None:
        return "unknown"
    return request.client.host
