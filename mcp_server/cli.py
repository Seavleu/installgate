"""CLI entry point (T11). Prints one GateVerdict and does not run the command."""

from __future__ import annotations

import asyncio
import sys

import typer
from contracts.contracts import GateVerdict
from rich.console import Console
from router.smoke import load_env_file

from mcp_server.check import check

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def callback() -> None:
    """Pre-install trust gate. Prints a verdict and does not run the command."""


def _show(verdict: GateVerdict) -> None:
    target = verdict.target
    version = f"=={target.version}" if target.version else ""
    calls = len(verdict.receipt.calls) if verdict.receipt else 0
    # Shown only in a terminal. A pipe stays one JSON document.
    if sys.stderr.isatty():
        typer.echo(
            f"{verdict.final_verdict.value}  {target.ecosystem.value}/{target.name}{version}"
            f"  next: {verdict.next_action}"
            f"  evidence: {len(verdict.evidence)}"
            f"  model calls: {calls}",
            err=True,
        )
    text = verdict.model_dump_json(indent=2)
    if sys.stdout.isatty():
        Console().print_json(text)
    else:
        typer.echo(text)


@app.command("check")
def check_command(install_command: str) -> None:
    """Return a GateVerdict for an install command."""
    _show(asyncio.run(check(install_command)))


def main() -> None:
    """Load `.env` from the current directory, then run. Existing variables win."""
    load_env_file()
    app()
