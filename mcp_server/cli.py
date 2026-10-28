"""CLI entry point (T11). Prints one GateVerdict and does not run the command."""

from __future__ import annotations

import asyncio

import typer

from mcp_server.check import check

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def callback() -> None:
    """Pre-install trust gate. Prints a verdict and does not run the command."""


@app.command("check")
def check_command(install_command: str) -> None:
    """Return a GateVerdict for an install command."""
    typer.echo(asyncio.run(check(install_command)).model_dump_json())


def main() -> None:
    app()
