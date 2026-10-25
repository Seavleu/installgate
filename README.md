# InstallGate

Pre-install check for coding agents. Reads metadata only. Never installs. Never runs the proposed command.

## Who does what

| Person | Folders | Do |
| --- | --- | --- |
| Kate | `engine/`, `validator/`, `eval/` | parsers, checks, policy, citations, benchmark |
| Jenny | `router/`, `remediate/`, `mcp_server/`, `ui/` | Nemotron, substitutes, API/CLI/MCP, UI |
| Both | `contracts/`, `docs/` | contracts freeze after day 1 — both must review changes |

Each folder has a short README. Empty files are yours to fill. Do not implement the other person's folders.

Full rules: `AGENTS.md`.

## Setup

```bash
uv sync --extra dev
cp .env.example .env
cd ui && pnpm install
```

Windows ARM: `tavily-python` needs a Rust build. Skip it for now (T08). If `uv run` tries to rebuild the env, use:

```powershell
uv run --no-sync pytest tests/test_token_factory.py
```

Keys go in `.env` only. Never commit secrets.

GitHub board (once, after the repo exists):

```bash
gh auth login
gh auth refresh -s project
PROJECT_NUMBER=10 ./setup-github.sh Seavleu/installgate
```

Do not re-run the issue step — it duplicates T01–T20. Then finish the 4 browser steps the script prints.

When both sides are wired:

```bash
docker compose up   # API :8000  UI :3000
```

## License

Apache-2.0
