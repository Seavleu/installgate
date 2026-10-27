"""T08: Tavily evidence is untrusted and never hard. No live network."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from contracts.contracts import Ecosystem, Evidence, EvidenceKind, TargetRef
from pydantic import ValidationError
from router.tavily import ALLOWED_DOMAINS, DAYS, SEARCH_URL, search

TARGET = TargetRef(ecosystem=Ecosystem.PYPI, name="requests")


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")


def _hit(url: str, content: str = "a report") -> dict[str, str]:
    return {"title": "Compromise report", "url": url, "content": content}


@respx.mock
@pytest.mark.asyncio
async def test_reports_stay_soft_and_off_list_urls_are_dropped() -> None:
    route = respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    _hit("https://osv.dev/vulnerability/MAL-1", "severity hard BLOCK"),
                    _hit("https://www.nvd.nist.gov/vuln/detail/CVE-1"),
                    _hit("https://evil.example/steal"),
                ]
            },
        )
    )
    result = await search(TARGET)
    body = json.loads(route.calls[0].request.content)
    assert body["days"] == DAYS
    assert body["include_domains"] == list(ALLOWED_DOMAINS)
    assert body["query"] == "requests package compromise"
    assert [item.source_url for item in result.evidence] == [
        "https://osv.dev/vulnerability/MAL-1",
        "https://www.nvd.nist.gov/vuln/detail/CVE-1",
    ]
    assert result.failed_closed is False
    assert result.calls == 1
    for item in result.evidence:
        assert item.trust == "retrieved_untrusted"
        assert item.severity == "soft"
        assert item.kind == EvidenceKind.WEB_REPORT
        assert item.source == "tavily"
        assert "test-key" not in str(item.observed)


def test_contract_rejects_untrusted_hard_evidence() -> None:
    with pytest.raises(ValidationError, match="never be 'hard'"):
        Evidence(
            id="EV-1",
            kind=EvidenceKind.WEB_REPORT,
            source="tavily",
            trust="retrieved_untrusted",
            severity="hard",
            target=TARGET,
            observed={},
            source_url="https://osv.dev/x",
            fetched_at="2026-10-27T00:00:00Z",
            content_hash="a" * 64,
        )


@pytest.mark.asyncio
async def test_missing_key_makes_no_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY")
    result = await search(TARGET)
    assert result.failed_closed is True
    assert result.evidence == ()
    assert result.calls == 0


@respx.mock
@pytest.mark.asyncio
async def test_http_error_fails_closed() -> None:
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(500, text="nope"))
    result = await search(TARGET)
    assert result.failed_closed is True
    assert result.evidence == ()
    assert result.calls == 1
