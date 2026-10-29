"""T14: spend cap, visitor limit, and demo snapshots. No live network."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from contracts.contracts import Verdict
from engine.cache import Cache
from fastapi.testclient import TestClient
from mcp_server.api import app, configure_logging
from mcp_server.check import check
from mcp_server.limit import Limiter, limiter
from mcp_server.samples import warm
from mcp_server.spend import add_spend, cap_usd, over_cap, spent_today, was_capped

MISSING = "pip install no-such-pkg-xyz"


@pytest.fixture
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CACHE_PATH", str(tmp_path / "gate.sqlite"))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    limiter.reset()


def test_spend_ledger_is_one_utc_day(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CACHE_PATH", str(tmp_path / "gate.sqlite"))
    monkeypatch.setenv("DAILY_SPEND_CAP_USD", "2")
    day = datetime(2026, 10, 29, 12, tzinfo=UTC)
    assert add_spend(1.5, day) == 1.5
    assert add_spend(0.5, day) == 2.0
    assert add_spend(0, day) == 2.0
    assert spent_today(day) == 2.0
    assert over_cap(day) is True
    assert spent_today(datetime(2026, 10, 30, tzinfo=UTC)) == 0.0
    assert cap_usd() == 2.0


def test_bad_cap_stops_the_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CACHE_PATH", str(tmp_path / "gate.sqlite"))
    monkeypatch.setenv("DAILY_SPEND_CAP_USD", "nope")
    assert cap_usd() == 0.0
    assert over_cap() is True


@respx.mock
@pytest.mark.usefixtures("_isolated")
async def test_spent_budget_keeps_the_block_and_skips_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DAILY_SPEND_CAP_USD", "0")

    def _boom(**kwargs: object) -> object:
        raise AssertionError("model must not be called once the budget is spent")

    monkeypatch.setattr("mcp_server.check.route", _boom)
    respx.get("https://pypi.org/pypi/no-such-pkg-xyz/json").mock(return_value=httpx.Response(404))
    respx.post("https://api.osv.dev/v1/query").mock(
        return_value=httpx.Response(200, json={"vulns": []})
    )

    verdict = await check(MISSING)
    assert verdict.final_verdict is Verdict.BLOCK
    assert verdict.evidence[0].kind.value == "not_found"
    assert verdict.receipt is not None
    assert verdict.receipt.calls == []
    assert was_capped() is True


@respx.mock
@pytest.mark.usefixtures("_isolated")
async def test_warm_samples_answer_requests_with_no_network(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "gate.sqlite")
    try:
        assert warm(cache) == 6
        assert warm(cache) == 0
    finally:
        cache.close()

    verdict = await check("pip install requests")
    assert verdict.final_verdict is Verdict.ALLOW
    assert verdict.target.version == "2.34.2"
    assert verdict.receipt is not None
    assert verdict.receipt.calls == []
    assert respx.calls.call_count == 0


def test_unreadable_ledger_counts_as_capped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CACHE_PATH", str(tmp_path / "gate.sqlite"))
    monkeypatch.setenv("DAILY_SPEND_CAP_USD", "5")
    (tmp_path / "spend.json").write_text('{"2026-10-29": 1.')
    assert over_cap() is True
    assert add_spend(0.25) == 5.25
    assert over_cap() is True


def test_ledger_write_leaves_no_temp_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CACHE_PATH", str(tmp_path / "gate.sqlite"))
    add_spend(0.1)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["spend.json"]


def test_limiter_forgets_idle_visitors_and_stays_bounded() -> None:
    small = Limiter(max_keys=3)
    for n in range(3):
        assert small.allow(f"10.0.0.{n}", limit=5, now=0.0)
    assert small.allow("10.0.0.9", limit=5, now=61.0)
    assert len(small) == 1
    for n in range(10):
        small.allow(f"10.0.1.{n}", limit=5, now=100.0 + n)
    assert len(small) <= 3


@pytest.mark.usefixtures("_isolated")
def test_spoofed_forwarded_for_does_not_reset_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    monkeypatch.setenv("RATE_LIMIT_TRUST_PROXY", "true")
    with TestClient(app) as client:
        first = client.post(
            "/check",
            json={"command": MISSING},
            headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.7"},
        )
        second = client.post(
            "/check",
            json={"command": MISSING},
            headers={"X-Forwarded-For": "2.2.2.2, 203.0.113.7"},
        )
    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.usefixtures("_isolated")
def test_api_configures_installgate_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = logging.getLogger("installgate")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setenv("LOG_LEVEL", "warning")
    with TestClient(app):
        assert logger.level == logging.WARNING
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    monkeypatch.setenv("LOG_LEVEL", "nonsense")
    configure_logging()
    assert logger.level == logging.INFO


@pytest.mark.usefixtures("_isolated")
def test_rate_limit_and_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    with TestClient(app) as client:
        assert client.get("/health").json() == {"ok": True}
        first = client.post("/check", json={"command": MISSING})
        second = client.post("/check", json={"command": MISSING})
    assert first.status_code == 200
    assert first.json()["final_verdict"] == "BLOCK"
    assert second.status_code == 429
