"""CLI entry point (T11). Prints one GateVerdict and does not run the command."""

from __future__ import annotations

import asyncio
import sys

from contracts.contracts import GateVerdict, Verdict
from rich.console import Console
from router.smoke import load_env_file

from mcp_server.check import check

_HELP = """\
Pre-install trust gate. Prints a verdict. Does not run the install.

  ig pip install reqeusts
  ig reqeusts
  ig npm install lodash

  eval "$(ig hook)"                 # then type `pip install …` as usual

Exit: 0 ALLOW, 1 REVIEW, 2 BLOCK. On ALLOW, `ig pip install x && pip install x` runs pip.
`installgate` is the same command.
"""

_INSTALLERS = frozenset(
    {"pip", "pip3", "python", "python3", "uv", "npm", "npx", "pnpm", "yarn", "docker"}
)


def command_from_argv(argv: list[str]) -> str:
    """Turn argv into one install command. A bare name means `pip install <name>`."""
    if not argv:
        raise ValueError("empty")
    if argv[0] == "check":
        rest = argv[1:]
        if not rest:
            raise ValueError("check needs an install command")
        return rest[0] if len(rest) == 1 else " ".join(rest)
    if argv[0] in _INSTALLERS or argv[0].upper() == "FROM":
        return " ".join(argv)
    if len(argv) == 1:
        return f"pip install {argv[0]}"
    return " ".join(argv)


def exit_code(verdict: Verdict) -> int:
    if verdict is Verdict.ALLOW:
        return 0
    if verdict is Verdict.BLOCK:
        return 2
    return 1


def hook_script() -> str:
    """bash/zsh: `pip install x` is checked, then the real pip runs only on ALLOW."""
    return """\
ig_wrap() {
  local bin="$1"
  shift
  case "$1" in
    install|i|add)
      command ig "$bin" "$@" || return $?
      ;;
  esac
  command "$bin" "$@"
}
pip()  { ig_wrap pip  "$@"; }
pip3() { ig_wrap pip3 "$@"; }
npm()  { ig_wrap npm  "$@"; }
"""


def _show(verdict: GateVerdict) -> None:
    target = verdict.target
    version = f"=={target.version}" if target.version else ""
    calls = len(verdict.receipt.calls) if verdict.receipt else 0
    if sys.stderr.isatty():
        print(
            f"{verdict.final_verdict.value}  {target.ecosystem.value}/{target.name}{version}"
            f"  next: {verdict.next_action}"
            f"  evidence: {len(verdict.evidence)}"
            f"  model calls: {calls}",
            file=sys.stderr,
        )
    text = verdict.model_dump_json(indent=2)
    if sys.stdout.isatty():
        Console().print_json(text)
    else:
        print(text)


def run(argv: list[str]) -> int:
    """Run one check from argv. Returns the process exit code."""
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(_HELP, end="")
        return 0 if argv else 2
    if argv[0] == "hook":
        print(hook_script(), end="")
        return 0
    try:
        command = command_from_argv(argv)
    except ValueError as exc:
        print(f"ig: {exc}", file=sys.stderr)
        print(_HELP, end="", file=sys.stderr)
        return 2
    verdict = asyncio.run(check(command))
    _show(verdict)
    return exit_code(verdict.final_verdict)


def main() -> None:
    """Load `.env` from the current directory, then run. Existing variables win."""
    load_env_file()
    raise SystemExit(run(sys.argv[1:]))
