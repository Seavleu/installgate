"""Per-call cost and the all-Ultra counterfactual (T07). Pure. No network."""

from __future__ import annotations

from contracts.contracts import ModelTier, RouteCall, RouterReceipt

# USD per 1M tokens, input / output. AGENTS.md price table.
_PER_MILLION: dict[ModelTier, tuple[float, float]] = {
    ModelTier.NANO: (0.06, 0.24),
    ModelTier.SUPER: (0.30, 0.90),
    ModelTier.ULTRA: (1.0, 3.0),
}
PRICE_TABLE_VERSION = "2026-10-25 token-factory-catalog"


def cost_usd(tier: ModelTier, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = _PER_MILLION[tier]
    return (prompt_tokens * pin + completion_tokens * pout) / 1_000_000


def build_receipt(
    calls: list[RouteCall],
    *,
    deterministic_only_ms: int,
    tavily_calls: int = 0,
) -> RouterReceipt:
    """Price `calls` at the tier that ran, and again as if every call had been Ultra."""
    total = sum(call.cost_usd for call in calls)
    counterfactual = sum(
        cost_usd(ModelTier.ULTRA, call.prompt_tokens, call.completion_tokens) for call in calls
    )
    savings = 0.0 if counterfactual == 0 else (counterfactual - total) / counterfactual * 100
    return RouterReceipt(
        calls=calls,
        total_cost_usd=total,
        counterfactual_all_ultra_usd=counterfactual,
        savings_pct=savings,
        price_table_version=PRICE_TABLE_VERSION,
        tavily_calls=tavily_calls,
        deterministic_only_ms=deterministic_only_ms,
    )
