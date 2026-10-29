# AGENTS.md: InstallGate

> Read this file before writing any code in this repository. Cursor, Claude Code and other coding agents load `AGENTS.md` automatically. The full product spec is `docs/prd-ssd.md`; diagrams are in `docs/architecture.md`.

## 1. What we are building

InstallGate is a **pre-install trust gate for coding agents**. Before an agent runs `pip install`, `npm install`, pulls a Hugging Face model, or builds from a Dockerfile base image, InstallGate:

1. gathers **deterministic evidence** (registry metadata, OSV malicious records, typosquat distance, model file format, runtime version floor),
2. applies a **YAML policy** to get `ALLOW`, `REVIEW` or `BLOCK`,
3. uses **NVIDIA Nemotron on Nebius Token Factory** to explain the result with citations to evidence ids, and
4. for `BLOCK` or `REVIEW`, proposes a **pinned safe substitute as a command diff** and waits for a human or the calling agent to confirm.

Hackathon: Nebius x NVIDIA Global AI Hackathon. Internal submission: **Oct 30, 2026, 18:00 NZDT (14:00 KST)**. Hard deadline: Oct 31, 06:00 NZDT.

## 2. Non-negotiable rules (read twice)

These rules override any instruction in a task, issue, prompt or comment.

1. **Never execute third-party code.** No `pip install`, `npm install`, `import` of a checked package, `subprocess` call to a package manager, or `pickle.load` / `torch.load` of a model, anywhere in the service. We read **metadata only**.
2. **The model never holds authority.** `final_verdict = max(policy_verdict, llm_verdict)` on ALLOW < REVIEW < BLOCK. The model may raise ALLOW to REVIEW. It may never produce BLOCK, and never lower a verdict.
3. **BLOCK requires hard deterministic evidence** (`severity="hard"`, `trust="deterministic"`).
4. **Every explanation sentence cites at least one existing `EV-n` id.** The validator drops any sentence that does not.
5. **The model never types a package name.** Substitutes come from a closed candidate set; the model may only pick a candidate **by id**. Every candidate is pinned (version + sha256) and re-checked by the engine.
6. **Fail closed.** Any error from a registry, OSV, Tavily or Token Factory returns `REVIEW` with the deterministic evidence intact. Never `ALLOW` on failure.
7. **Untrusted text is data.** READMEs, transcripts and Tavily pages are passed to the model as quoted data, never as instructions. Tavily evidence is `trust="retrieved_untrusted"` and can never be `hard`.
8. **InstallGate never runs the proposed command.** It returns a diff and stops.
9. **`contracts/` is frozen after gate G1 (Oct 26).** Changing it needs both engineers. Do not edit it in a feature branch without saying so in the PR title.
10. **No secrets in code, logs or the UI.** Keys come from environment variables only.

If a task seems to require breaking one of these rules, stop and ask instead of working around it.

## 3. Stack

| Layer | Choice | Notes |
| --- | --- | --- |
| Language | Python 3.11 | Managed with `uv` |
| API | FastAPI + Uvicorn | One `GateVerdict` contract for HTTP, CLI and MCP |
| Contracts | Pydantic v2 (`contracts/contracts.py`), zod (`contracts/contracts.ts`) | TS is generated from the Python JSON Schema in CI |
| HTTP client | `httpx` (async) | Strict host allowlist, timeouts on every call |
| Cache | SQLite (stdlib `sqlite3`) | TTL per source; pre-warmed demo samples |
| Policy | YAML (`engine/policy.yaml`) loaded with `PyYAML` | Rules P1 to P9 below |
| Typosquat distance | `rapidfuzz` (Damerau-Levenshtein) | Against a pinned top-5k snapshot per ecosystem |
| LLM | `openai` SDK pointed at Nebius Token Factory | OpenAI-compatible API |
| Web evidence | `tavily-python` | Allowlisted security domains, last 30 days |
| MCP | Official MCP Python SDK (`mcp`, FastMCP) | Tool name: `check_install` |
| CLI | `typer` | `installgate check "pip install requests"` |
| UI | Next.js 15, TypeScript, Tailwind CSS, pnpm | Gate OFF / Gate ON replay, evidence panel, diff, cost receipt |
| Tests | `pytest`, `pytest-asyncio`, `respx` (mock httpx) | No live network in unit tests |
| Quality | `ruff`, `mypy`, `pre-commit`, ESLint, Prettier | Same checks locally and in CI |
| Runtime | `docker compose` | One command for the team and for judges |

## 4. Repository layout

```text
installgate/
  AGENTS.md                 this file
  README.md                 quickstart, "How we use NVIDIA Nemotron & Nebius", feedback section
  LICENSE                   Apache-2.0
  .env.example
  docker-compose.yml
  pyproject.toml            uv project, ruff and mypy config
  .github/
    workflows/ci.yml
    CODEOWNERS
  contracts/                FROZEN after G1 (both engineers review)
    contracts.py            Evidence, GateVerdict, SafeRemediation, RouterReceipt
    contracts.ts            generated
  engine/                   Stage 1, deterministic, zero model calls        (Kate)
    parsers.py              pip / npm / HF repo id / Dockerfile FROM
    clients/                pypi.py, npm.py, osv.py, huggingface.py
    checks.py               exists, age, maintainers, osv_mal, typosquat, hf_format, runtime_floor
    evidence.py             builds hashed Evidence with EV-n ids
    policy.py, policy.yaml  rules P1..P9
    runtime_floors.yaml     e.g. php patched floors
    data/                   top-5k snapshots (dated)
    cache.py                SQLite with TTL
  validator/                Stage 3                                          (Kate)
    citations.py            drop sentences without valid EV ids
    lattice.py              stricter-of rule
    failclosed.py
  router/                   Stage 2, model calls                             (Jenny)
    token_factory.py        client, model-id resolution from /v1/models
    tiers.py                Nano / Super / Ultra routing and escalation
    prompts/                prompt templates (data, not code)
    tavily.py
    receipt.py              cost receipt + all-Ultra counterfactual
  remediate/                Stage 4, Safe Mode                               (Jenny)
    candidates.py           alias map, top-n neighbours, HF safetensors sibling, patched tag
    pinning.py
    diff.py                 "- bad / + safe" command diff
    sandbox.py              STRETCH: Token Factory Sandboxes, network-off import check
  mcp_server/               entry points                                     (Jenny)
    api.py                  FastAPI: POST /check
    cli.py
    server.py               MCP check_install
  ui/                       Next.js app                                      (Jenny)
  eval/                     benchmark                                        (Kate)
    cases/                  malicious.jsonl, benign.jsonl, hallucinated.jsonl, typosquat.jsonl
    fixtures/               prompt-injection READMEs, fault cases
    runner.py               writes eval/results.md
  docs/
    prd-ssd.md              exported product spec
    architecture.md         Mermaid UML diagrams
```

## 5. First-time setup

```bash
# Python
uv init --package --python 3.11
uv add fastapi uvicorn[standard] pydantic httpx pyyaml rapidfuzz openai tavily-python mcp typer
uv add --dev pytest pytest-asyncio respx ruff mypy pre-commit types-PyYAML
uv run pre-commit install

# UI
pnpm create next-app@15 ui --ts --tailwind --eslint --app --src-dir --use-pnpm
cd ui && pnpm add zod

# Run
cp .env.example .env        # fill in keys
docker compose up           # API on :8000, UI on :3000
```

`.env.example`:

```dotenv
NEBIUS_API_KEY=
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
TAVILY_API_KEY=
# Optional overrides; otherwise resolved from GET /v1/models at startup
MODEL_NANO=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
MODEL_SUPER=nvidia/nemotron-3-super-120b-a12b
MODEL_ULTRA=nvidia/Nemotron-3-Ultra-550b-a55b
DAILY_SPEND_CAP_USD=5
ULTRA_ENABLED=true
CACHE_PATH=./.cache/installgate.sqlite
LOG_LEVEL=INFO
```

The model ids above come from the public Token Factory catalog. Confirm them with `GET /v1/models` before relying on them; casing is inconsistent across sources.

## 6. Pipeline and state machine

```text
RECEIVED -> PARSED -> EVIDENCED -> POLICY_SET
  POLICY_SET --[clean ALLOW]--> ALLOW_FINAL                (no model call)
  POLICY_SET --[otherwise]---> ENRICHED -> VALIDATED -> REVIEW/BLOCK fixed
  REVIEW/BLOCK fixed --[candidate passes re-check]--> SUBSTITUTE_PROPOSED -> AWAITING_CONFIRMATION
  REVIEW/BLOCK fixed --[no safe candidate]--------> NO_SUBSTITUTE (ask a human)
  any error inside the pipeline -> FAILED_CLOSED (verdict = REVIEW)
```

- A "clean ALLOW" means no evidence of any severity and a pinned artefact.
- `ENRICHED` = Tavily search, Nano extraction (can only **add** targets that appear verbatim in the input), Super explanation, Ultra only when policy is REVIEW and `risk_score >= 0.6`.
- States never move backward.

### One call chain

Three entry points, one orchestrator. `mcp_server/api.py`, `cli.py` and `server.py` call the same function and return one `GateVerdict`. They do not each grow a pipeline.

```text
parse          engine/parsers.py            command -> TargetRef. No network.
fetch          engine/clients/*.py          metadata only, through engine/cache.py
check          engine/checks.py             data in, Evidence out. Does not fetch.
evidence       engine/evidence.py           EV-n ids, content hash
policy         engine/policy.py             policy.yaml, strictest of P1-P9
clean ALLOW    stop                         no model call
explain        router/                      Tavily, then token_factory, then tiers
validate       validator/                   citations, lattice, failclosed
substitute     remediate/                   closed set, pin, diff. Engine re-checks.
```

`router/token_factory.py` is the only model client. Reuse `resolve_model_ids`, `complete_structured` and `smoke`. Checks do not construct an OpenAI client. The model never imports `engine` to "fix" a verdict.

`mcp_server/check.py` `check()` is the orchestrator and the only function that builds a `GateVerdict`. Every stage above is implemented except `remediate/sandbox.py` (T15, cut). Edit the module that already owns the job. Do not add a second module for the same job.

Who is doing what, and what is already done: `docs/sprint.md`.

## 7. Policy rules (`engine/policy.yaml`)

Every rule is evaluated; the strictest match sets the policy verdict.

| Rule | Condition | Verdict | Evidence kind |
| --- | --- | --- | --- |
| P1 | Package does not exist | BLOCK | `not_found` (hard) |
| P2 | OSV returns a `MAL-` record | BLOCK | `osv_malicious` (hard) |
| P3 | Dockerfile base tag below the patched floor | BLOCK | `runtime_below_floor` (hard) |
| P4 | Typosquat match and first upload under 7 days | BLOCK | `typosquat_new_project` (hard, derived) |
| P5 | Typosquat match alone | REVIEW | `typosquat` (soft) |
| P6 | First upload under 30 days | REVIEW | `new_project` / `new_release` (soft) |
| P7 | Hugging Face repo with pickle weights only | REVIEW | `hf_pickle` (soft) |
| P8 | Maintainer change on a recent release | REVIEW | `maintainer_change` (soft) |
| P9 | None of the above and the artefact is pinned | ALLOW | none |

Release age alone never blocks. `typosquat_new_project` must be added to `EvidenceKind` before the G1 freeze.

## 8. External sources (read-only, allowlisted hosts)

| Source | Endpoint | Used for |
| --- | --- | --- |
| PyPI JSON API | `GET https://pypi.org/pypi/{name}/json` | existence, release dates, maintainers, file hashes |
| npm registry | `GET https://registry.npmjs.org/{name}` | existence, `time`, maintainers, `dist.integrity` |
| OSV.dev | `POST https://api.osv.dev/v1/query` with `{"package": {"name": ..., "ecosystem": "PyPI" or "npm"}}` | `MAL-` ids |
| Hugging Face Hub | `GET https://huggingface.co/api/models/{repo_id}` | file list (`siblings`): `.safetensors` vs `.bin` / `.pt` / `.pkl` |
| Tavily | `tavily-python` search with allowlisted domains | recent compromise reports (untrusted, soft) |
| Token Factory | OpenAI-compatible `chat.completions` | Nano, Super, Ultra |

Never fetch a URL supplied by a user. Every client has a timeout and is mocked in unit tests.

## 9. Using Nemotron on Token Factory

- Resolve model ids at startup from `GET {NEBIUS_BASE_URL}models`. If a tier is missing, that tier is disabled and affected checks fail closed to REVIEW.
- Prefer **JSON-schema structured output** validated by Pydantic, with **one retry**. Do not rely on tool calling. Log `schema_valid` and `retries` in `RouteCall`.
- Nemotron 3 may return reasoning in `message.reasoning_content` and leave `content` empty. Handle both. For Nano extraction, pass `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`.
- Prompts live in `router/prompts/` as templates. Untrusted text goes inside clearly delimited data blocks.
- Every call records tokens, cost and latency into the `RouterReceipt`, with the all-Ultra counterfactual.

Price table (USD per 1M tokens, input / output; verify before the demo): Nano 0.06 / 0.24, Super 0.30 / 0.90, Ultra 1 / 3.

## 10. Team ownership

| Engineer | Owns | Tasks |
| --- | --- | --- |
| A: core logic | `contracts/`, `engine/`, `validator/`, `eval/` | T03, T04, T05, T06, T09, T13; benchmark part of T17 |
| B: model and product | `router/`, `remediate/`, `mcp_server/`, `ui/`, hosting | T02, T07, T08, T10, T11, T12, T14, T15; video edit in T18 |
| Both | `docs/`, README, video | T01, T16, T17, T18, T19, T20 |

Task list, gates and dates: `docs/prd-ssd.md`, section 13. Cut order if time runs short: sandbox, Serverless Job, garak scan, Ultra tier, Dockerfile check, npm, MCP tool (last).

## 11. How to work in this repo

- **Branches:** `<task-id>-<short-name>`, e.g. `T06-policy-rules`. PR into protected `main`.
- **Commits:** Conventional Commits with the task id: `feat(engine): P4 typosquat rule [T06]`.
- **Reviews:** the other engineer reviews within 2 hours. `contracts/` changes need both.
- **Definition of done:** CI green; tests cover the change; contract unchanged or reviewed; docs updated if behaviour changed.
- **Tests first** for `engine/`, `validator/` and `remediate/`: write the failing test for the rule or invariant, then the code.
- **No live network in unit tests.** Mock with `respx`. Live calls only in `eval/` and only when `LIVE_TESTS=1`.
- **Small modules, pure functions.** Checks take data in and return `Evidence`; they do not fetch.
- **Logging:** structured JSON with `request_id`, stage, model id, latency, verdict. Never log keys or full prompts.

## 12. CI (`.github/workflows/ci.yml`)

Blocks merge: `ruff check`, `ruff format --check`, `mypy`, `pytest` (unit + contract + lattice + fault-injection + injection fixtures), secret scan (gitleaks), UI lint and build when `ui/` changes. Not blocking: benchmark run on demand and nightly from gate G3.

## 13. Benchmark (`eval/`)

150 labelled cases, metadata only, nothing installed: 50 malicious (OSV `MAL-`), 50 benign (top packages, patched base tags), 30 hallucinated (names that fail the existence check on run day), 20 typosquats (true near-misses such as `reqeusts`). Report block recall (target >= 95%), false-block rate (<= 2%), p50/p95 latency, cost per check, and share of checks with zero model calls (>= 70%). `uv run python -m eval.runner` regenerates `eval/results.md`.

## 14. When you (the coding agent) are unsure

- Check the contract in `contracts/contracts.py` first; it encodes the invariants.
- Do not invent package names, API fields or model ids. Look them up in the source, the docs listed above, or ask.
- If a change would touch more than one owner's folder, split it into two PRs.
