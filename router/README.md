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

## T08 (this task)

`search` in `tavily.py`. The query is the package name. Results come from allowlisted security domains, last 30 days. Each hit is `trust="retrieved_untrusted"` and `severity="soft"`. A page that says "hard" cannot change that. An off-list URL is dropped. A missing key or an HTTP error returns no evidence and `failed_closed=True`.

```bash
uv run --no-sync pytest tests/test_tavily.py -v
```

## Model comparison

`compare.py` runs routed Nemotron against up to three rivals from the catalog. Stage 1 runs once per case, so every system sees the same policy verdict and `EV-n` ids. Each system goes through the production `route()` and the same validator. Only the model ids change, through `MODEL_*` overrides that `resolve_model_ids` accepts only when the catalog lists them. Temperature is 0. The run stops by whole case at `DAILY_SPEND_CAP_USD`. ALLOW cases never reach a model; five run as a control.

```bash
uv run python -m router.compare --dry-run          # case plan, no network
LIVE_TESTS=1 uv run python -m router.compare       # writes eval/results-models.md
uv run --no-sync pytest tests/test_compare.py      # mocked
```

Rivals have no listed price, so the report gives their tokens only. It does not overwrite `eval/results.md`, which is Stage 1 only.

## Later

| File | Task |
| --- | --- |
| `prompts/rank_substitute.txt` | T10 rank by candidate id only |
