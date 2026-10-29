"""MCP entry point (T11). Tool name: check_install."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from mcp_server.check import check

server = MCPServer("installgate")


@server.tool(name="check_install", structured_output=False)
async def check_install(command: str) -> str:
    """Check an install command. Returns a GateVerdict. Does not run the command."""
    return (await check(command)).model_dump_json()


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
