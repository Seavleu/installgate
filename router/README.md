# router/ — Jenny

Stage 2. NVIDIA Nemotron on Nebius Token Factory.

| File | Build this |
| --- | --- |
| `token_factory.py` | OpenAI-compatible client. Resolve model ids from `GET /v1/models` at startup |
| `tiers.py` | Nano extract → Super explain. Ultra only if policy is REVIEW and risk ≥ 0.6 |
| `tavily.py` | Web search. Trust = untrusted. Never hard evidence |
| `receipt.py` | Token cost + all-Ultra counterfactual |
| `prompts/` | Templates. Untrusted text is data, not instructions |

Keys from env only. JSON-schema output. One retry. Fail closed to REVIEW if Token Factory is down.

Tasks: T07, T08.
