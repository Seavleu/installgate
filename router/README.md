# router/ — Jenny

Stage 2. NVIDIA Nemotron on Nebius Token Factory. Keys from env only.

## T02 (this task)

Resolve model ids from `GET /v1/models` through the OpenAI SDK (`AsyncOpenAI` on `NEBIUS_BASE_URL`). Smoke-test Nano and Super and log **model ids, tokens, latency** for each. A missing tier is skipped. Never log the API key.

```bash
cp .env.example .env   # fill NEBIUS_API_KEY
uv run python -m router.smoke
```

Unit tests mock HTTP (no live network):

```bash
uv run --no-sync pytest tests/test_token_factory.py
```

If a tier is missing from the catalog, that tier is disabled. Catalog/HTTP errors fail closed.

## T07 (this task)

`route` in `tiers.py`. A clean ALLOW makes no model call. Otherwise Nano extracts names that appear verbatim in the input, Super explains with `EV-n` ids, and Ultra runs only when policy is `REVIEW` and risk ≥ 0.6. `receipt.py` prices each call and the all-Ultra counterfactual. The model may return ALLOW or REVIEW. It cannot BLOCK. Errors fail closed to REVIEW.

```bash
uv run --no-sync pytest tests/test_router.py
```

Does not edit `contracts/`. T03 is still open.

## Later

| File | Task |
| --- | --- |
| `tavily.py` | T08 untrusted web evidence, never hard |
| `prompts/rank_substitute.txt` | T10 rank by candidate id only |
