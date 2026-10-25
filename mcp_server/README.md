# mcp_server/ — Jenny

Same `GateVerdict` for HTTP, CLI, and MCP.

| File | Build this |
| --- | --- |
| `api.py` | FastAPI `POST /check` |
| `cli.py` | `installgate check "pip install requests"` |
| `server.py` | MCP tool `check_install` |

Call engine → router → validator → remediate. Do not install anything. Return a diff and stop.

Tasks: T11, T12.
