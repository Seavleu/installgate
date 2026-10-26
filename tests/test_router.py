"""T07: Nano, Super, Ultra only on REVIEW >= 0.6, and the cost receipt. No live network."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from contracts.contracts import ModelTier, RouteCall, Verdict
from router.receipt import build_receipt, cost_usd
from router.tiers import route

BASE = "https://api.tokenfactory.nebius.com/v1/"
NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
SUPER = "nvidia/nemotron-3-super-120b-a12b"
ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"


def _model(model_id: str) -> dict[str, object]:
    return {"id": model_id, "object": "model", "created": 0, "owned_by": "nvidia"}


CATALOG = {
    "object": "list",
    "data": [_model(NANO), _model(SUPER), _model(ULTRA)],
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.setenv("NEBIUS_BASE_URL", BASE)
    monkeypatch.setenv("ULTRA_ENABLED", "true")
    monkeypatch.delenv("MODEL_NANO", raising=False)
    monkeypatch.delenv("MODEL_SUPER", raising=False)
    monkeypatch.delenv("MODEL_ULTRA", raising=False)


def _completion(content: str, model_id: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0, "total_tokens": 1_000_000},
    }


def _explain(verdict: str = "REVIEW", evidence_id: str = "EV-1") -> str:
    return json.dumps(
        {
            "llm_verdict": verdict,
            "sentences": [{"text": "Cited.", "evidence_ids": [evidence_id]}],
        }
    )


def test_receipt_prices_the_same_tokens_as_ultra() -> None:
    call = RouteCall(
        stage="extract",
        tier=ModelTier.NANO,
        model_id=NANO,
        prompt_tokens=1_000_000,
        completion_tokens=0,
        cost_usd=cost_usd(ModelTier.NANO, 1_000_000, 0),
        latency_ms=1,
    )
    receipt = build_receipt([call], deterministic_only_ms=4)
    assert receipt.total_cost_usd == pytest.approx(0.06)
    assert receipt.counterfactual_all_ultra_usd == pytest.approx(1.0)
    assert receipt.savings_pct == pytest.approx(94.0)
    assert receipt.deterministic_only_ms == 4


@pytest.mark.asyncio
async def test_allow_makes_no_model_call() -> None:
    result = await route(
        policy_verdict=Verdict.ALLOW,
        risk_score=0.0,
        evidence_ids=[],
        command="pip install requests==2.32.3",
    )
    assert result.failed_closed is False
    assert result.llm_verdict == Verdict.ALLOW
    assert result.receipt.calls == []
    assert result.receipt.total_cost_usd == 0


@respx.mock
@pytest.mark.asyncio
async def test_review_below_threshold_skips_ultra() -> None:
    respx.get(f"{BASE}models").mock(return_value=httpx.Response(200, json=CATALOG))
    posts = respx.post(f"{BASE}chat/completions").mock(
        side_effect=[
            httpx.Response(200, json=_completion('{"targets": ["requests"]}', NANO)),
            httpx.Response(200, json=_completion(_explain(), SUPER)),
        ]
    )
    result = await route(
        policy_verdict=Verdict.REVIEW,
        risk_score=0.59,
        evidence_ids=["EV-1"],
        command="pip install requests",
    )
    assert [json.loads(call.request.content)["model"] for call in posts.calls] == [NANO, SUPER]
    assert result.failed_closed is False
    assert result.llm_verdict == Verdict.REVIEW
    assert result.added_targets == ("requests",)
    assert result.explanation[0].evidence_ids == ["EV-1"]
    assert result.receipt.total_cost_usd == pytest.approx(0.06 + 0.30)
    assert result.receipt.counterfactual_all_ultra_usd == pytest.approx(2.0)
    assert "test-key" not in str(result.as_log())


@respx.mock
@pytest.mark.asyncio
async def test_review_at_threshold_calls_ultra_and_drops_invented_names() -> None:
    respx.get(f"{BASE}models").mock(return_value=httpx.Response(200, json=CATALOG))
    posts = respx.post(f"{BASE}chat/completions").mock(
        side_effect=[
            httpx.Response(
                200, json=_completion('{"targets": ["requests", "not-in-the-input"]}', NANO)
            ),
            httpx.Response(200, json=_completion(_explain("ALLOW", "EV-9"), SUPER)),
            httpx.Response(200, json=_completion(_explain("REVIEW", "EV-1"), ULTRA)),
        ]
    )
    result = await route(
        policy_verdict=Verdict.REVIEW,
        risk_score=0.6,
        evidence_ids=["EV-1"],
        command="pip install requests",
    )
    sent = [json.loads(call.request.content)["model"] for call in posts.calls]
    assert sent == [NANO, SUPER, ULTRA]
    assert result.added_targets == ("requests",)
    assert result.llm_verdict == Verdict.REVIEW
    assert [sentence.evidence_ids for sentence in result.explanation] == [["EV-1"]]
    assert result.receipt.calls[-1].stage == "escalate"
    assert result.receipt.calls[-1].escalation_reason is not None


@respx.mock
@pytest.mark.asyncio
async def test_block_does_not_call_ultra() -> None:
    respx.get(f"{BASE}models").mock(return_value=httpx.Response(200, json=CATALOG))
    posts = respx.post(f"{BASE}chat/completions").mock(
        side_effect=[
            httpx.Response(200, json=_completion('{"targets": []}', NANO)),
            httpx.Response(200, json=_completion(_explain("ALLOW"), SUPER)),
        ]
    )
    result = await route(
        policy_verdict=Verdict.BLOCK,
        risk_score=0.9,
        evidence_ids=["EV-1"],
        command="pip install requests",
    )
    assert len(posts.calls) == 2
    assert result.llm_verdict == Verdict.ALLOW
    assert result.failed_closed is False


@respx.mock
@pytest.mark.asyncio
async def test_bad_json_retries_once() -> None:
    respx.get(f"{BASE}models").mock(return_value=httpx.Response(200, json=CATALOG))
    posts = respx.post(f"{BASE}chat/completions").mock(
        side_effect=[
            httpx.Response(200, json=_completion("nope", NANO)),
            httpx.Response(200, json=_completion('{"targets": []}', NANO)),
            httpx.Response(200, json=_completion(_explain(), SUPER)),
        ]
    )
    result = await route(
        policy_verdict=Verdict.BLOCK,
        risk_score=0.1,
        evidence_ids=["EV-1"],
        command="pip install requests",
    )
    assert len(posts.calls) == 3
    assert result.failed_closed is False
    assert result.receipt.calls[0].retries == 1
    assert result.receipt.calls[0].schema_valid is False


@respx.mock
@pytest.mark.asyncio
async def test_missing_super_fails_closed() -> None:
    respx.get(f"{BASE}models").mock(
        return_value=httpx.Response(200, json={"object": "list", "data": [_model(NANO)]})
    )
    result = await route(
        policy_verdict=Verdict.REVIEW,
        risk_score=0.1,
        evidence_ids=["EV-1"],
        command="pip install requests",
    )
    assert result.failed_closed is True
    assert result.llm_verdict == Verdict.REVIEW
    assert result.receipt.calls == []


@pytest.mark.asyncio
async def test_disabled_ultra_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ULTRA_ENABLED", "false")
    result = await route(
        policy_verdict=Verdict.REVIEW,
        risk_score=0.6,
        evidence_ids=["EV-1"],
        command="pip install requests",
    )
    assert result.failed_closed is True
    assert result.llm_verdict == Verdict.REVIEW
