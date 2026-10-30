# Contributing

## Setup

```bash
git clone https://github.com/Seavleu/installgate.git
cd installgate
uv sync --extra dev
cp .env.example .env
source .venv/bin/activate
```

## Checks

Same as CI:

```bash
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
```

No live network in unit tests. Mock with `respx`. Do not commit `.env`.

Read `AGENTS.md` before changing engine, policy, or contracts. `contracts/` is frozen unless both engineers agree.

## CLI vs API

- Default install is the CLI + MCP (`ig`, `installgate-mcp`).
- HTTP API needs the `server` extra (`fastapi`, `uvicorn`).
- Docker Compose uses `--extra server`.

## Pull requests

- Branch: `<task-id>-<short-name>` when following the PRD, otherwise a short name.
- Conventional Commits: `feat(engine): …`, `fix(cli): …`, `docs: …`.
- One concern per PR.

## Release

You run this locally so the commit author is you, not an editor. Steps: [`docs/RELEASE.md`](docs/RELEASE.md).
