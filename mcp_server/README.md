# mcp_server/ — Jenny

Same `GateVerdict` for HTTP, CLI, and MCP.

| File | Build this |
| --- | --- |
| `api.py` | FastAPI `POST /check`. Does not read `.env`; keys come from the process environment (`env_file` in `docker-compose.yml`, or `export` before `uvicorn`). |
| `cli.py` | `installgate check "pip install requests"`. Reads `.env` in the current directory. |
| `server.py` | MCP tool `check_install`, `python -m mcp_server.server` |

`check` in `check.py` is the only function that builds a `GateVerdict`. `POST /check`, `installgate check`, and the MCP tool `check_install` call it and stop. They do not run the command.

```bash
uv run --no-sync pytest tests/test_gate.py -v
```

`POST /check` is limited per visitor (`RATE_LIMIT_PER_MINUTE`). The model budget is `DAILY_SPEND_CAP_USD` for the UTC day; past that, the decision engine still answers. Startup writes the three demo snapshots into the cache when they are missing. `GET /health` is the probe.

Tasks: T11, T12, T14.
