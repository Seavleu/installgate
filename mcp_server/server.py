"""MCP entry point (T11). Tool name: check_install."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from mcp_server.agent import payload
from mcp_server.check import check

server = MCPServer("installgate")


@server.tool(name="check_install", structured_output=False)
async def check_install(command: str) -> str:
    """Check one install command. Returns GateVerdict plus pinned_command. Does not run it."""
    verdict = await check(command)
    return json.dumps(payload(verdict, command), separators=(",", ":"))


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
