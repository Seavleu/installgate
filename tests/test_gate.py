"""T11: HTTP, CLI, and MCP return one GateVerdict. No live network."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
import respx
from contracts.contracts import Verdict
from fastapi.testclient import TestClient
from mcp_server.api import app as api_app
from mcp_server.check import check
from mcp_server.cli import app as cli_app
from mcp_server.server import server
from router.receipt import build_receipt
from router.tiers import RouteResult
from typer.testing import CliRunner

SHA = "ab" * 32
MISSING = "pip install no-such-pkg-xyz"


def _core(payload: dict[str, object]) -> dict[str, object]:
    evidence = payload["evidence"]
    assert isinstance(evidence, list)
    remediation = payload.get("remediation") or {}
    assert isinstance(remediation, dict)
    target = payload["target"]
    assert isinstance(target, dict)
    return {
        "policy_verdict": payload["policy_verdict"],
        "llm_verdict": payload["llm_verdict"],
        "final_verdict": payload["final_verdict"],
        "outcome": payload["outcome"],
        "failed_closed": payload["failed_closed"],
        "next_action": payload["next_action"],
        "target_name": target["name"],
        "evidence": [
            {"id": item["id"], "kind": item["kind"], "severity": item["severity"]}
            for item in evidence
            if isinstance(item, dict)
        ],
        "remediation_status": remediation.get("status"),
    }


def _pypi(name: str, *, found: bool) -> dict[str, object]:
    if not found:
        return {}
    return {
        "info": {"version": "2.32.3", "author": "psf"},
        "releases": {
            "2.32.3": [
                {
                    "upload_time_iso_8601": "2020-01-01T00:00:00Z",
                    "digests": {"sha256": SHA},
                }
            ]
        },
    }


@pytest.fixture
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CACHE_PATH", str(tmp_path / "gate.sqlite"))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)


def _fake_route(**kwargs: object) -> object:
    async def _inner() -> RouteResult:
        return RouteResult(
            llm_verdict=Verdict.REVIEW,
            added_targets=(),
            explanation=(),
            receipt=build_receipt(
                [],
                deterministic_only_ms=int(kwargs.get("deterministic_only_ms") or 0),
                tavily_calls=int(kwargs.get("tavily_calls") or 0),
            ),
            failed_closed=False,
        )

    return _inner()


@respx.mock
@pytest.mark.usefixtures("_isolated")
def test_three_entry_points_share_one_block_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_server.check.route", _fake_route)
    respx.get("https://pypi.org/pypi/no-such-pkg-xyz/json").mock(return_value=httpx.Response(404))
    respx.post("https://api.osv.dev/v1/query").mock(
        return_value=httpx.Response(200, json={"vulns": []})
    )

    http = TestClient(api_app).post("/check", json={"command": MISSING})
    assert http.status_code == 200
    cli = CliRunner().invoke(cli_app, ["check", MISSING])
    assert cli.exit_code == 0, cli.output
    mcp = asyncio.run(server.call_tool("check_install", {"command": MISSING}))
    assert mcp.is_error is False
    block = mcp.content[0]
    text = block.text if hasattr(block, "text") else str(block)

    cores = [
        _core(http.json()),
        _core(json.loads(cli.output)),
        _core(json.loads(text)),
    ]
    assert cores[0] == cores[1] == cores[2]
    assert cores[0]["final_verdict"] == "BLOCK"
    assert cores[0]["evidence"] == [{"id": "EV-1", "kind": "not_found", "severity": "hard"}]
    assert cores[0]["next_action"] == "ask_human"


@respx.mock
@pytest.mark.usefixtures("_isolated")
async def test_registry_error_fails_closed_to_review(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**kwargs: object) -> object:
        raise AssertionError("model must not be called when the registry failed")

    monkeypatch.setattr("mcp_server.check.route", _boom)
    respx.get("https://pypi.org/pypi/requests/json").mock(return_value=httpx.Response(500))

    verdict = await check("pip install requests")
    assert verdict.failed_closed is True
    assert verdict.final_verdict is Verdict.REVIEW
    assert verdict.evidence == []
    assert verdict.next_action == "ask_human"


@respx.mock
@pytest.mark.usefixtures("_isolated")
async def test_clean_allow_makes_no_model_call() -> None:
    respx.get("https://pypi.org/pypi/requests/json").mock(
        return_value=httpx.Response(200, json=_pypi("requests", found=True))
    )
    respx.post("https://api.osv.dev/v1/query").mock(
        return_value=httpx.Response(200, json={"vulns": []})
    )

    verdict = await check("pip install requests")
    assert verdict.final_verdict is Verdict.ALLOW
    assert verdict.outcome.value == "ALLOW"
    assert verdict.failed_closed is False
    assert verdict.next_action == "proceed"
    assert verdict.receipt is not None
    assert verdict.receipt.calls == []
    assert verdict.target.version == "2.32.3"
    assert verdict.target.artifact_sha256 == SHA


@respx.mock
@pytest.mark.usefixtures("_isolated")
async def test_alias_substitute_is_pinned_after_recheck(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_server.check.route", _fake_route)

    def _get(request: httpx.Request) -> httpx.Response:
        name = request.url.path.split("/")[2]
        return httpx.Response(200, json=_pypi(name, found=True))

    respx.get(url__regex=r"https://pypi\.org/pypi/.*/json").mock(side_effect=_get)
    respx.post("https://api.osv.dev/v1/query").mock(
        return_value=httpx.Response(200, json={"vulns": []})
    )

    verdict = await check("pip install reqeusts")
    assert verdict.final_verdict is Verdict.REVIEW
    assert verdict.outcome.value == "VERIFIED_SUBSTITUTE"
    assert verdict.next_action == "use_substitute"
    assert verdict.remediation is not None
    assert verdict.remediation.candidate is not None
    assert verdict.remediation.candidate.name == "requests"
    assert verdict.remediation.approved_requirement is not None
    assert "requests==2.32.3" in verdict.remediation.approved_requirement
    assert "reqeusts" not in (verdict.remediation.approved_requirement or "")
