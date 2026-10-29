"""Nano extract, Super explain, Ultra only when policy is REVIEW and risk >= 0.6 (T07)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from contracts.contracts import (
    ExplanationSentence,
    ModelTier,
    RouteCall,
    RouterReceipt,
    Verdict,
)
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from router.receipt import build_receipt, cost_usd
from router.token_factory import (
    SMOKE_TIMEOUT_S,
    TokenFactoryError,
    _openai,
    complete_structured,
    resolve_model_ids,
)

_log = logging.getLogger("installgate.router")
_PROMPTS = Path(__file__).parent / "prompts"
_ULTRA_RISK = 0.6


class _Extract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: list[str] = Field(default_factory=list)


class _Sentence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    evidence_ids: list[str]


class _Explain(BaseModel):
    model_config = ConfigDict(extra="forbid")
    llm_verdict: Literal["ALLOW", "REVIEW"]
    sentences: list[_Sentence] = Field(default_factory=list)


@dataclass(frozen=True)
class RouteResult:
    llm_verdict: Verdict
    added_targets: tuple[str, ...]
    explanation: tuple[ExplanationSentence, ...]
    receipt: RouterReceipt
    failed_closed: bool
    dropped_sentences: int = 0

    def as_log(self) -> dict[str, Any]:
        return {
            "stage": "route",
            "llm_verdict": self.llm_verdict.value,
            "failed_closed": self.failed_closed,
            "dropped_sentences": self.dropped_sentences,
            "total_cost_usd": self.receipt.total_cost_usd,
            "counterfactual_all_ultra_usd": self.receipt.counterfactual_all_ultra_usd,
            "savings_pct": self.receipt.savings_pct,
            "calls": [
                {
                    "stage": call.stage,
                    "tier": call.tier.value,
                    "model_id": call.model_id,
                    "prompt_tokens": call.prompt_tokens,
                    "completion_tokens": call.completion_tokens,
                    "cost_usd": call.cost_usd,
                    "latency_ms": call.latency_ms,
                    "schema_valid": call.schema_valid,
                    "retries": call.retries,
                }
                for call in self.receipt.calls
            ],
        }


def _ultra_enabled() -> bool:
    return os.environ.get("ULTRA_ENABLED", "true").strip().lower() not in {"0", "false", "no"}


def _data(body: str) -> list[dict[str, str]]:
    template = (_PROMPTS / "explain.txt").read_text(encoding="utf-8").strip()
    return [
        {"role": "system", "content": template},
        {"role": "user", "content": f"<data>\n{body}\n</data>"},
    ]


def _extract_messages(body: str) -> list[dict[str, str]]:
    template = (_PROMPTS / "extract.txt").read_text(encoding="utf-8").strip()
    return [
        {"role": "system", "content": template},
        {"role": "user", "content": f"<data>\n{body}\n</data>"},
    ]


def _keep_sentences(
    sentences: list[_Sentence], evidence_ids: set[str]
) -> tuple[ExplanationSentence, ...]:
    kept: list[ExplanationSentence] = []
    for sentence in sentences:
        ids = sentence.evidence_ids
        if sentence.text and len(sentence.text) <= 400 and ids and set(ids) <= evidence_ids:
            kept.append(ExplanationSentence(text=sentence.text, evidence_ids=ids))
    return tuple(kept)


def _call(
    *,
    stage: Literal["extract", "explain", "escalate"],
    tier: ModelTier,
    model_id: str,
    meta_prompt_tokens: int,
    meta_completion_tokens: int,
    latency_ms: int,
    schema_valid: bool,
    retries: int,
    escalation_reason: str | None = None,
) -> RouteCall:
    return RouteCall(
        stage=stage,
        tier=tier,
        model_id=model_id,
        prompt_tokens=meta_prompt_tokens,
        completion_tokens=meta_completion_tokens,
        cost_usd=cost_usd(tier, meta_prompt_tokens, meta_completion_tokens),
        latency_ms=latency_ms,
        escalation_reason=escalation_reason,
        schema_valid=schema_valid,
        retries=retries,
    )


def _logged(result: RouteResult) -> RouteResult:
    _log.info(json.dumps(result.as_log(), separators=(",", ":")))
    return result


async def route(
    *,
    policy_verdict: Verdict,
    risk_score: float,
    evidence_ids: list[str],
    command: str,
    untrusted_text: str = "",
    deterministic_only_ms: int = 0,
    tavily_calls: int = 0,
    client: AsyncOpenAI | None = None,
    temperature: float | None = None,
) -> RouteResult:
    """Model calls for a non-ALLOW check. The model may raise ALLOW to REVIEW. It cannot BLOCK.

    A clean ALLOW makes no model call. Ultra runs only when policy is REVIEW and risk >= 0.6.
    A Token Factory error returns REVIEW with failed_closed set. The validator applies the lattice.
    """
    if policy_verdict == Verdict.ALLOW:
        result = RouteResult(
            llm_verdict=Verdict.ALLOW,
            added_targets=(),
            explanation=(),
            receipt=build_receipt(
                [], deterministic_only_ms=deterministic_only_ms, tavily_calls=tavily_calls
            ),
            failed_closed=False,
        )
        return _logged(result)

    need_ultra = policy_verdict == Verdict.REVIEW and risk_score >= _ULTRA_RISK
    if need_ultra and not _ultra_enabled():
        result = RouteResult(
            llm_verdict=Verdict.REVIEW,
            added_targets=(),
            explanation=(),
            receipt=build_receipt(
                [], deterministic_only_ms=deterministic_only_ms, tavily_calls=tavily_calls
            ),
            failed_closed=True,
        )
        return _logged(result)

    api = client
    opened: AsyncOpenAI | None = None
    calls: list[RouteCall] = []
    try:
        if api is None:
            api = _openai(timeout=SMOKE_TIMEOUT_S)
            opened = api
        ids = await resolve_model_ids(api)
        if ids.nano is None or ids.super is None or (need_ultra and ids.ultra is None):
            raise TokenFactoryError("required model tier is missing")
        source = f"{command}\n{untrusted_text}"
        extracted, nano_meta = await complete_structured(
            api,
            model=ids.nano,
            messages=_extract_messages(source),
            schema=_Extract,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            temperature=temperature,
        )
        calls.append(
            _call(
                stage="extract",
                tier=ModelTier.NANO,
                model_id=ids.nano,
                meta_prompt_tokens=nano_meta.prompt_tokens,
                meta_completion_tokens=nano_meta.completion_tokens,
                latency_ms=nano_meta.latency_ms,
                schema_valid=nano_meta.schema_valid,
                retries=nano_meta.retries,
            )
        )
        added = tuple(target for target in extracted.targets if target and target in source)
        known = set(evidence_ids)
        explain_body = (
            f"command: {command}\npolicy_verdict: {policy_verdict.value}\n"
            f"risk_score: {risk_score}\nevidence_ids: {', '.join(evidence_ids)}\n"
            f"untrusted:\n{untrusted_text}"
        )
        explained, super_meta = await complete_structured(
            api,
            model=ids.super,
            messages=_data(explain_body),
            schema=_Explain,
            temperature=temperature,
        )
        calls.append(
            _call(
                stage="explain",
                tier=ModelTier.SUPER,
                model_id=ids.super,
                meta_prompt_tokens=super_meta.prompt_tokens,
                meta_completion_tokens=super_meta.completion_tokens,
                latency_ms=super_meta.latency_ms,
                schema_valid=super_meta.schema_valid,
                retries=super_meta.retries,
            )
        )
        verdict = Verdict(explained.llm_verdict)
        sentences = _keep_sentences(explained.sentences, known)
        dropped = len(explained.sentences) - len(sentences)
        if need_ultra:
            assert ids.ultra is not None
            escalated, ultra_meta = await complete_structured(
                api,
                model=ids.ultra,
                messages=_data(explain_body),
                schema=_Explain,
                temperature=temperature,
            )
            calls.append(
                _call(
                    stage="escalate",
                    tier=ModelTier.ULTRA,
                    model_id=ids.ultra,
                    meta_prompt_tokens=ultra_meta.prompt_tokens,
                    meta_completion_tokens=ultra_meta.completion_tokens,
                    latency_ms=ultra_meta.latency_ms,
                    schema_valid=ultra_meta.schema_valid,
                    retries=ultra_meta.retries,
                    escalation_reason="policy is REVIEW and risk_score >= 0.6",
                )
            )
            if escalated.llm_verdict == "REVIEW":
                verdict = Verdict.REVIEW
            ultra_sentences = _keep_sentences(escalated.sentences, known)
            if ultra_sentences:
                sentences = ultra_sentences
                dropped = len(escalated.sentences) - len(ultra_sentences)
        result = RouteResult(
            llm_verdict=verdict,
            added_targets=added,
            explanation=sentences,
            receipt=build_receipt(
                calls, deterministic_only_ms=deterministic_only_ms, tavily_calls=tavily_calls
            ),
            failed_closed=False,
            dropped_sentences=dropped,
        )
        return _logged(result)
    except TokenFactoryError:
        result = RouteResult(
            llm_verdict=Verdict.REVIEW,
            added_targets=(),
            explanation=(),
            receipt=build_receipt(
                calls, deterministic_only_ms=deterministic_only_ms, tavily_calls=tavily_calls
            ),
            failed_closed=True,
        )
        return _logged(result)
    finally:
        if opened is not None:
            await opened.close()
