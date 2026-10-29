"""Live model comparison, mocked. Stage 1 is frozen; only model ids change. No live network."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from contracts.contracts import Verdict
from eval.runner import load_cases
from router import compare

BASE = "https://api.tokenfactory.nebius.com/v1/"
NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
SUPER = "nvidia/nemotron-3-super-120b-a12b"
ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"
RIVAL = "Qwen/Qwen3-30B-A3B-Instruct-2507"


def _model(model_id: str) -> dict[str, object]:
    return {"id": model_id, "object": "model", "created": 0, "owned_by": "test"}


CATALOG = {"object": "list", "data": [_model(NANO), _model(SUPER), _model(ULTRA), _model(RIVAL)]}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.setenv("NEBIUS_BASE_URL", BASE)
    monkeypatch.setenv("ULTRA_ENABLED", "true")
    for key in ("MODEL_NANO", "MODEL_SUPER", "MODEL_ULTRA", "LIVE_TESTS"):
        monkeypatch.delenv(key, raising=False)


def _reply(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    model = body["model"]
    schema = body["response_format"]["json_schema"]["name"]
    assert body.get("temperature") == 0.0
    if schema == "_Extract":
        content = json.dumps({"targets": []})
    else:
        # The rival answers below the policy; both cite one real id and one made-up id.
        content = json.dumps(
            {
                "llm_verdict": "ALLOW" if model == RIVAL else "REVIEW",
                "sentences": [
                    {"text": "Cited [EV-1].", "evidence_ids": ["EV-1"]},
                    {"text": "Invented [EV-99].", "evidence_ids": ["EV-99"]},
                ],
            }
        )
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
        },
    )


def test_plan_is_fixed_and_offline() -> None:
    plan = compare.select(load_cases(), "README TEXT")
    buckets = [case.bucket for case in plan]
    for bucket, count in compare.BUCKETS:
        assert buckets.count(bucket) == count
    assert buckets.count("REVIEW injection") == 1
    again = compare.select(load_cases(), "README TEXT")
    assert [c.case_id for c in plan] == [c.case_id for c in again]
    injected = next(case for case in plan if case.injection)
    base = next(case for case in plan if case.case_id == injected.case_id.split("+")[0])
    assert [e.id for e in injected.evidence] == [e.id for e in base.evidence]
    assert injected.policy is base.policy


@respx.mock
async def test_rivals_share_frozen_stage1_and_the_lattice_holds() -> None:
    respx.get(f"{BASE}models").mock(return_value=httpx.Response(200, json=CATALOG))
    respx.post(f"{BASE}chat/completions").mock(side_effect=_reply)

    result = await compare.run(cap_usd=100.0, temperature=0.0)

    names = [system.name for system in result.systems]
    assert names == ["Nemotron (routed)", RIVAL]
    assert result.skipped == [m for m, _ in compare.RIVAL_CANDIDATES if m != RIVAL]
    assert not result.stopped_at_cap

    model_cases = [case for case in result.cases if case.policy is not Verdict.ALLOW]
    for system in names:
        rows = [row for row in result.rows if row.system == system]
        assert [row.case_id for row in sorted(rows, key=lambda r: r.case_id)] == sorted(
            case.case_id for case in model_cases
        )
        assert all(row.final is row.policy for row in rows)
        assert all(row.kept == 1 and row.dropped_router == 1 for row in rows)
        assert all(row.dropped_validator == 0 for row in rows)

    rival_rows = [row for row in result.rows if row.system == RIVAL]
    assert all(row.lowered for row in rival_rows)
    assert all(row.calls for row in result.rows)
    assert all(not row.calls and row.final is Verdict.ALLOW for row in result.controls)

    text = compare.render(result)
    assert "no price listed" in text
    assert "`Qwen/Qwen3-30B-A3B-Instruct-2507`" in text
    assert "test-key" not in text


@respx.mock
async def test_spend_cap_stops_whole_cases() -> None:
    respx.get(f"{BASE}models").mock(return_value=httpx.Response(200, json=CATALOG))
    respx.post(f"{BASE}chat/completions").mock(side_effect=_reply)

    result = await compare.run(cap_usd=0.0, temperature=0.0)

    assert result.stopped_at_cap
    assert result.rows == []
    assert "The run stopped at the cap." in compare.render(result)


def test_live_run_needs_the_flag(capsys: pytest.CaptureFixture[str]) -> None:
    assert compare.main([]) == 2
    assert "LIVE_TESTS=1" in capsys.readouterr().err
    assert compare.main(["--dry-run"]) == 0
    assert "BLOCK not_found" in capsys.readouterr().out
