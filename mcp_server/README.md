# mcp_server/ — Jenny

Same `GateVerdict` for HTTP, CLI, and MCP.

| File | Build this |
| --- | --- |
| `api.py` | FastAPI `POST /check` |
| `cli.py` | `installgate check "pip install requests"` |
| `server.py` | MCP tool `check_install` |

`check` in `check.py` is the only function that builds a `GateVerdict`. `POST /check`, `installgate check`, and the MCP tool `check_install` call it and stop. They do not run the command.

```bash
uv run --no-sync pytest tests/test_gate.py -v
```

Tasks: T11, T12.
