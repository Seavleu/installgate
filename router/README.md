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

## Later

| File | Task |
| --- | --- |
| `tiers.py` | T07 Nano → Super; Ultra only if REVIEW and risk ≥ 0.6 |
| `tavily.py` | T08 untrusted web evidence, never hard |
| `receipt.py` | T07 cost + all-Ultra counterfactual |
| `prompts/` | T07 templates; untrusted text is data |
