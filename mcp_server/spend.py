"""Daily model budget (T14). The decision engine still runs when the budget is spent."""

from __future__ import annotations

import json
import os
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

_capped: ContextVar[bool] = ContextVar("installgate_spend_capped", default=False)


def reset_capped() -> None:
    _capped.set(False)


def mark_capped() -> None:
    _capped.set(True)


def was_capped() -> bool:
    return _capped.get()


def ledger_path() -> Path:
    cache = Path(os.environ.get("CACHE_PATH", "./.cache/installgate.sqlite"))
    return cache.with_name("spend.json")


def cap_usd() -> float:
    raw = os.environ.get("DAILY_SPEND_CAP_USD", "5")
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return value if value >= 0 else 0.0


def _day(now: datetime | None) -> str:
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).date().isoformat()


def _read() -> dict[str, float]:
    path = ledger_path()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in loaded.items():
        if isinstance(key, str) and isinstance(value, int | float):
            out[key] = float(value)
    return out


def spent_today(now: datetime | None = None) -> float:
    return _read().get(_day(now), 0.0)


def over_cap(now: datetime | None = None) -> bool:
    return spent_today(now) >= cap_usd()


def add_spend(amount: float, now: datetime | None = None) -> float:
    """Add a model cost to today's total. A non-positive amount is ignored."""
    day = _day(now)
    current = _read().get(day, 0.0)
    if amount <= 0:
        return current
    updated = current + amount
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({day: updated}))
    return updated
