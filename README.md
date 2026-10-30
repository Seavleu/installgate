<p align="center">
  <img src="docs/logo.svg" alt="InstallGate" width="112" height="112">
</p>

<h1 align="center">InstallGate</h1>

<p align="center">
  <b>A pre-install trust gate for coding agents</b>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-3776AB" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-green" alt="Apache-2.0"></a>
  <a href="https://github.com/Seavleu/installgate/actions/workflows/ci.yml"><img src="https://github.com/Seavleu/installgate/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Seavleu/installgate"><img src="https://img.shields.io/badge/CLI-ig-14171C" alt="CLI ig"></a>
  <a href="https://tokenfactory.nebius.com/"><img src="https://img.shields.io/badge/Nebius%20×%20NVIDIA-hackathon-7C3AED" alt="Nebius × NVIDIA hackathon"></a>
</p>

InstallGate is a pre-install trust gate for coding agents. You give it one `pip install` or `npm install` command. It reads registry metadata, applies a fixed policy, and returns one verdict: **ALLOW**, **REVIEW**, or **BLOCK**.

It does not install the package. It does not run the command it proposes. A block or a review can include a pinned substitute as a command diff. A person, or the calling agent, confirms that command before it is used anywhere else.

Built for the Nebius x NVIDIA hackathon. The explanation step uses NVIDIA Nemotron on Nebius Token Factory. The decision itself does not.

## Install

Python 3.11+. Package: [`installgate` on PyPI](https://pypi.org/project/installgate/).

```bash
uv tool install installgate
uv tool update-shell          # once; then open a new terminal
ig --version                  # installgate 0.1.3
```

```bash
uv tool install 'installgate[tavily]'   # web evidence
uv tool install 'installgate[server]'   # HTTP API (FastAPI)
```

`pipx install installgate` works if you have pipx. If `ig` already exists on your PATH:

```bash
uv tool install --force installgate
```

`--no` checks only. It never runs pip or npm. Press **n** if a prompt appears.

Optional keys in the environment, or a `.env` in the current directory:

```bash
export NEBIUS_API_KEY=...     # explanations on REVIEW/BLOCK. ALLOW does not need it.
export TAVILY_API_KEY=...     # optional web evidence; untrusted, never a BLOCK
```

## Usage

```bash
ig --no pip install requests              # ALLOW, pin, no model; rerun is cached
ig --no pip install reqeusts              # BLOCK typo; substitute is pinned requests
ig --no pip install no-such-pkg-xyz       # BLOCK, no substitute
ig --no npm install lodash                # ALLOW (exists + pin)
ig --no npm install totally-fake-npm-xyz  # BLOCK
ig --no pip install requests numpy        # abort: one package per check
```

```bash
ig pip install reqeusts       # same, may prompt [Y/n] on ALLOW
ig reqeusts                   # same as pip install reqeusts
ig --json --no pip install requests
ig --help
ig --version
eval "$(ig completion zsh)"    # bash|zsh|fish
installgate-mcp                # MCP stdio
```

Exit: `0` ALLOW, `1` REVIEW, `2` BLOCK.

Wrap your real pip/npm in this shell (ALLOW then runs your pip; REVIEW/BLOCK stop):

```bash
eval "$(ig hook)"
pip install reqeusts
```

From this repo instead of PyPI: `uv tool install --force .`

Agent playbook: [`docs/playbook.md`](docs/playbook.md).

## What you get back

Every entry point returns the same `GateVerdict`.

| Field | Meaning |
| --- | --- |
| `final_verdict` | `ALLOW`, `REVIEW`, or `BLOCK`. The stricter of the policy and the model. |
| `evidence` | Facts gathered for this check, each with an `EV-n` id. |
| `explanation` | Sentences that cite those ids. A sentence with no valid id is dropped. |
| `remediation` | A pinned substitute, when one survives a second check. |
| `next_action` | `proceed`, `use_substitute`, `ask_human`, or `abort`. |
| `receipt` | Tokens, cost, and the cost if every model call had been Ultra. |

## How a check works

```text
parse one pip or npm install command
  → fetch registry metadata and query OSV
  → run the deterministic checks
  → apply policy P1–P10, strictest match wins
  → ALLOW with a pin and no findings: stop, no model call
  → otherwise: optional web search, then Nemotron, then citation checks
  → if the verdict is not ALLOW: propose a pinned substitute and re-check it
  → return the verdict and stop
```

The same checks cover Hugging Face repos and Dockerfile `FROM` lines. Those paths are in the engine and in the benchmark. The command, the HTTP API, and the MCP tool accept pip and npm.

A registry error, a model error, or a missing key fails closed to **REVIEW** and keeps whatever evidence was already collected. A **BLOCK** that already has hard evidence stays a block.

The model may raise ALLOW to REVIEW. BLOCK comes only from the policy, and only from hard deterministic evidence. Web pages are quoted to the model as data. They are stored as untrusted, soft evidence.

## Policy

Every rule runs. The strictest match wins. Policy version `2026-10-30.1`.

| Rule | Condition | Verdict |
| --- | --- | --- |
| P1 | Package does not exist | BLOCK |
| P2 | OSV returns a `MAL-` record | BLOCK |
| P3 | Dockerfile base tag is below the patched floor | BLOCK |
| P4 | Typosquat of a popular name, first upload under 7 days | BLOCK |
| P5 | Typosquat alone | REVIEW |
| P6 | First upload under 30 days | REVIEW |
| P7 | Hugging Face repo with pickle weights and no safetensors file | REVIEW |
| P8 | Maintainer change on a recent release | REVIEW |
| P9 | No findings, and the artefact is pinned | ALLOW |
| P10 | A check could not run | REVIEW |

An allow requires a pin: version plus sha256, or a Hugging Face revision. Stage 1 attaches the registry pin, so `pip install numpy` can ALLOW. An unpinned package with no findings and no hash is a review. A fresh release of an established project is not P6; a brand-new name is. Release age alone never blocks. npm has no typosquat snapshot; a name that exists and pins still ALLOWs (P9). A name that does not exist BLOCKs (P1).

## Develop from source

```bash
uv sync --extra dev
cp .env.example .env
source .venv/bin/activate
```

`ig` is then on PATH from this venv. Keys in `.env` are read from the current directory. The API process does not load that file unless you export it:

```bash
set -a && source .env && set +a
uv run uvicorn mcp_server.api:app --port 8000
```

### HTTP

```bash
uv run uvicorn mcp_server.api:app --port 8000
```

```bash
curl -s -X POST http://127.0.0.1:8000/check \
  -H 'Content-Type: application/json' \
  -d '{"command":"pip install requests"}'
```

`GET /health` returns `{"ok": true}`. Interactive docs are at `http://127.0.0.1:8000/docs`. There is no account.

### Page

The page shows the same command twice: the line an agent would run, and the verdict beside it.

```bash
cd ui && pnpm install && pnpm dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). The page calls `/api/check`, which the Next.js server forwards to `API_URL` (default `http://127.0.0.1:8000`). Start the API first.

### MCP

The tool name is `check_install`. It takes one `command` string (one package). The JSON is a `GateVerdict` plus `pinned_command` (copy-paste on ALLOW), `substitute_command`, and `decided_by`. Policy always wins. It speaks stdio, from the repo root, so `uv` can see the project:

From PyPI:

```bash
uvx --from installgate python -m mcp_server.server
```

From this repo:

```bash
uv run python -m mcp_server.server
```

A client such as Cursor registers that command and then calls `check_install` before it installs anything. InstallGate still only returns the verdict. Company paste-in: [docs/playbook.md](docs/playbook.md).

```json
{
  "mcpServers": {
    "installgate": {
      "command": "uv",
      "args": ["run", "python", "-m", "mcp_server.server"]
    }
  }
}
```

### Docker

```bash
cp .env.example .env    # fill in the keys
docker compose up -d --build
```

Three containers. `caddy` is the only public entry: the page is on [http://localhost](http://localhost) (port 80). It forwards to `ui`, which forwards `/api/check`, `/api/check/stream`, and `/api/mcp` to `api` at `http://api:8000`. The API is published on `127.0.0.1:8000` only (`API_PORT` changes the host port), for local tools. No login.

Both app containers run as non-root users and have a health check on `/health` (API) and `/` (page). The page waits for a healthy API; Caddy waits for a healthy page. `docker compose ps` shows the state.

### Deploy

One Linux VM with Docker and the Compose plugin is enough. On the server:

```bash
git clone https://github.com/Seavleu/installgate.git && cd installgate
git checkout <tag>                      # the tag you demo from
cp .env.example .env && chmod 600 .env  # keys, SITE_ADDRESS
docker compose up -d --build
docker compose ps                       # api, ui healthy; caddy running
curl -fsS https://<your-domain>/        # the page
```

Set `SITE_ADDRESS` in `.env` to your domain, and point the domain's DNS A record at the server before starting. Caddy then gets an HTTPS certificate on its own; ports 80 and 443 must be open. Leave `SITE_ADDRESS=:80` to serve plain HTTP on the server's IP.

The rate limit keys on the rightmost `X-Forwarded-For` entry, which Caddy writes. Keep Caddy as the only public port; the API port is bound to localhost.

Roll back by checking out the previous tag and running `docker compose up -d --build` again. The cache volume can be deleted at any time (`docker compose down -v`); it refills from the registries. To stop model spend at once, set `DAILY_SPEND_CAP_USD=0` and run `docker compose up -d`: checks keep returning the policy verdict.

On startup the API writes three demo snapshots into the cache when those keys are empty: `requests`, `reqeusts`, and `no-such-pkg-xyz`. The `requests` snapshot was read from the PyPI JSON API on 2026-10-29 (version 2.34.2). A later live fetch replaces a snapshot after its cache TTL.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEBIUS_API_KEY` | empty | Token Factory credential. Required for a model call. |
| `NEBIUS_BASE_URL` | `https://api.tokenfactory.nebius.com/v1/` | OpenAI-compatible base URL. |
| `TAVILY_API_KEY` | empty | Web evidence. Missing key: no web evidence, and a review or block is marked `failed_closed`. The verdict is unchanged. |
| `MODEL_NANO` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Override. Otherwise resolved from `GET /v1/models`. |
| `MODEL_SUPER` | `nvidia/nemotron-3-super-120b-a12b` | Override. |
| `MODEL_ULTRA` | `nvidia/Nemotron-3-Ultra-550b-a55b` | Override. |
| `ULTRA_ENABLED` | `true` | Ultra runs only for policy REVIEW at risk ≥ 0.6. |
| `DAILY_SPEND_CAP_USD` | `5` | Model budget for the UTC day. After it is spent, checks still return the policy verdict and skip the model. |
| `RATE_LIMIT_PER_MINUTE` | `30` | `POST /check` calls per visitor. `0` disables the limit. |
| `RATE_LIMIT_TRUST_PROXY` | `false` | Key the limit on the rightmost `X-Forwarded-For` entry. Compose sets this on the API, behind Caddy. |
| `CACHE_PATH` | `./.cache/installgate.sqlite` | SQLite cache of registry summaries. |
| `LOG_LEVEL` | `INFO` | JSON lines on stderr from the API. Keys and prompts are not logged. |
| `SITE_ADDRESS` | `:80` | Compose only. A domain name turns on automatic HTTPS in Caddy. |
| `API_PORT` | `8000` | Compose only. Host port for the API, bound to `127.0.0.1`. |

## How we use NVIDIA Nemotron and Nebius

Nemotron runs on Nebius Token Factory through the OpenAI SDK. Model ids come from `GET /v1/models` on the first call that needs them. A tier missing from the catalog is turned off for that process.

| Tier | Role |
| --- | --- |
| Nano | Reads the command. It may add a target only when that exact name already appears in the input. Thinking is disabled for this call. |
| Super | Writes the explanation. |
| Ultra | Runs only when the policy verdict is REVIEW, the risk score is at least 0.6, and `ULTRA_ENABLED` is true. |

Calls use JSON schema output, with one retry. Nemotron sometimes puts the answer in `reasoning_content` and leaves `content` empty; both are read.

Each call is priced on the receipt, and priced again as if it had been Ultra. The table is `2026-10-25 token-factory-catalog`, USD per 1M tokens, input / output:

| Tier | Input | Output |
| --- | --- | --- |
| Nano | 0.06 | 0.24 |
| Super | 0.30 | 0.90 |
| Ultra | 1 | 3 |

A live ping of Nano and Super, which prints model ids, tokens, and latency:

```bash
uv run python -m router.smoke
```

Tavily is not a model. It searches `osv.dev`, `nvd.nist.gov`, `cisa.gov`, `github.blog`, and `thehackernews.com` for the last 30 days. Those hits cannot be hard evidence.

## Substitutes

Substitutes come from a closed list: a known alias, a near neighbour in the popularity snapshot, a Hugging Face safetensors sibling, or a patched Dockerfile tag. The model is not asked to invent a package name. The alias shipped today is `reqeusts` → `requests`. It is chosen by rule.

A candidate is shown only after the decision engine checks it again and the re-check is an allow. The diff is the original command beside the pinned requirement (`name==version` and a sha256). InstallGate stops there.

The note on a substitute is import compatibility only. Behavioural equivalence is not guaranteed. A network-off sandbox import of that pin is a stretch goal and is not in this build.

## Benchmark

150 labelled cases. Metadata only: nothing is installed, imported, or executed. The run below is deterministic. It does not call Nemotron, so it has no model-cost figure and no share-of-checks-with-zero-model-calls figure. Latency is Stage 1 alone.

```bash
uv run pytest -q
uv run python -m eval.runner   # offline; rewrites eval/results.md
```

The runner never touches the network. The label scripts do. Run them by hand, never in CI. Each accepts `--dry-run`:

- `eval/fetch_osv_malicious.py`
- `eval/fetch_top_pypi.py`
- `eval/verify_labels.py`
- `eval/add_cases.py`

### Cases

| Class | Cases | Source |
| --- | --- | --- |
| benign | 44 | 29 PyPI installs (19 pinned, 10 unpinned) with dates from the PyPI JSON API; 5 Hugging Face repos with safetensors only; 10 Docker base images pinned to a patch-level tag |
| malicious | 50 | OSV `MAL-` records from `ossf/malicious-packages` at commit `323d867`. 24 names have since been removed, 1 is still published, 25 simulate the registry before removal |
| hallucinated | 30 | Names that returned 404 on the PyPI JSON API on the day of the run |
| typosquat | 20 | Near-misses of the top-5000 PyPI snapshot (`hugovk/top-pypi-packages`) |
| hf_pickle | 5 | Hugging Face repos with pickle weights and no safetensors file |
| floating_tag | 1 | `alpine:3.20`, a base tag with no patch release |

### Results

Recorded on 2026-10-30. Regenerate with `uv run python -m eval.runner`. The full report, including the confusion matrix, is [`eval/results.md`](eval/results.md).

| Metric | Target | Result |
| --- | --- | --- |
| Block recall | ≥ 95% | 100.0% |
| False-block rate on benign | ≤ 2% | 0.0% |
| Review rate on benign | no target | 0.0% |
| p50 latency | — | 0.02 ms |
| p95 latency | — | 0.71 ms |

| Class | Deciding rule | Every rule that fired |
| --- | --- | --- |
| benign | P9 ×44 | P9 ×44 |
| malicious | P2 ×26, P1 ×24 | P2 ×26, P1 ×24, P5 ×3, P6 ×1 |
| hallucinated | P1 ×30 | P1 ×30 |
| typosquat | P4 ×13, P5 ×7 | P5 ×20, P4 ×13, P6 ×13 |
| hf_pickle | P7 ×5 | P7 ×5 |
| floating_tag | P10 ×1 | P10 ×1 |

| Class | Cases | Passed | Failed | Labels |
| --- | --- | --- | --- | --- |
| benign | 44 | 44 | 0 | 10 unverified |
| malicious | 50 | 50 | 0 | 25 unverified |
| hallucinated | 30 | 30 | 0 | verified |
| typosquat | 20 | 20 | 0 | 20 unverified |
| hf_pickle | 5 | 5 | 0 | verified |
| floating_tag | 1 | 1 | 0 | 1 unverified |

"Deciding rule" is the strictest rule that matched. "Passed" means the verdict matched the label.

`numpy`, `django`, `fastapi`, `pydantic`, and `sqlalchemy` ALLOW: they are established projects, Stage 1 pins the latest artefact, and a fresh release is not P6. A compromised update is still P2 (`MAL-`) or P8 (maintainer change). Brand-new names stay P6. 150/150 passed. False-block rate 0%.

### Limits of this run

- Stage 1 only. No model cost, and no measurement of how often a live check skips the model.
- 25 of the 50 malicious cases simulate the registry before the package was removed. Recall there shows that the OSV path is wired, not that those names were still installable on the day of the run.
- npm is not in the benchmark. Exists + pin still ALLOW (`test_npm_lodash_pinned_is_allow` in `tests/test_policy.py`); there is no npm typosquat snapshot.
- A floating base tag such as `python:3.12-slim` is a review by design.
- Only the PHP floors are verified against a vendor advisory (2026-10-21). Other image floors in `engine/runtime_floors.yaml` are placeholders.

### Model comparison

A separate live run measures Stage 2. Routed Nemotron and three catalog rivals (`Qwen/Qwen3-30B-A3B-Instruct-2507`, `openai/gpt-oss-120b`, `Qwen/Qwen3-235B-A22B-Instruct-2507`) answer 21 BLOCK and REVIEW cases, with the same frozen Stage 1, the same prompts, and the same validator. Report: [`eval/results-models.md`](eval/results-models.md). Method: [`router/README.md`](router/README.md#model-comparison).

```bash
LIVE_TESTS=1 uv run python -m router.compare
```

On 2026-10-29 every system kept the policy verdict on all 21 cases, and no call needed a retry. Routed Nemotron explained all 21 cases (25 cited sentences, none dropped) at a model cost of $0.008. `Qwen/Qwen3-30B-A3B-Instruct-2507` failed closed once and answered ALLOW on 4 REVIEW cases, which the lattice ignored. An earlier run the same day, before `explain.txt` asked for the `EV-n` id inside the sentence text, dropped most sentences in the citation check.

## Developer feedback

What we would tell the next person who puts a model behind a gate that already has a verdict:

- Run the policy first. Give the model no way to type a package name. Our substitute list is closed, and the one alias is accepted only after a second deterministic check.
- Keep a sentence only when it cites an evidence id this check actually produced. On a missing package the model still ran, and the explanation stayed empty, because nothing it wrote cited `EV-1`.
- Skip the model on a clean allow. That is the common path, and it is why a pinned `requests` install comes back with a $0 receipt.
- Hand registry text and web pages to the model as quoted data. A page that urges a block stays soft evidence.

## Responsible use

InstallGate reads registry metadata. It does not install a package, import it, or execute the command it prints. A block requires hard deterministic evidence from the policy. Confirm a substitute before running it. The substitute is pinned to a version and a sha256.

The public page has no account. `POST /check` is limited per visitor per minute, and `DAILY_SPEND_CAP_USD` caps model spend for the UTC day. Past the cap, the policy verdict is what you get.

## Development

| Area | Path |
| --- | --- |
| Contracts | `contracts/` |
| Parse, fetch, policy | `engine/` |
| Citations, lattice, fail-closed | `validator/` |
| Nemotron, Tavily, receipts | `router/` |
| Substitutes and diffs | `remediate/` |
| HTTP, CLI, MCP | `mcp_server/` |
| Page | `ui/` |
| Benchmark | `eval/` |

`AGENTS.md` is the rule set for anyone changing the code. `docs/architecture.md` is the pipeline diagram. Each folder has a short README and the test command for that area.

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
cd ui && pnpm lint && pnpm build
```

Unit tests mock HTTP with `respx`. They do not call PyPI, OSV, Tavily, or Token Factory. Live calls belong in `router.smoke` and in the label scripts, and only when you mean to make them.

On Windows ARM, `tavily-python` needs a Rust build. Leave it uninstalled and run `uv run --no-sync` so uv does not try to rebuild the environment.

The GitHub board is created once:

```bash
gh auth login
gh auth refresh -s project
PROJECT_NUMBER=10 ./setup-github.sh Seavleu/installgate
```

Running the issue step again duplicates T01–T20.

## License

[Apache-2.0](LICENSE)
