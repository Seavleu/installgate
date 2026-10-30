"""CLI entry point (T11). Prints one GateVerdict. On ALLOW, may exec pip after confirm."""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from contracts.contracts import Ecosystem, GateVerdict, Verdict
from router.smoke import load_env_file

from mcp_server.check import check
from mcp_server.render import print_header, print_stage, print_verdict

_HELP = """\
ig — pre-install trust gate. Prints a verdict. Does not import the package.

Usage:
  ig pip install numpy           # then [Y/n] to run pinned pip
  ig -y pip install numpy        # run if ALLOW, no prompt
  ig --no pip install numpy      # check only
  ig --json pip install numpy
  ig --version

  eval "$(ig hook)"              # `pip install` checks, then real pip on ALLOW

Exit: 0 ALLOW, 1 REVIEW, 2 BLOCK. `installgate` is the same command.
"""

_INSTALLERS = frozenset(
    {"pip", "pip3", "python", "python3", "uv", "npm", "npx", "pnpm", "yarn", "docker"}
)


def package_version() -> str:
    try:
        return version("installgate")
    except PackageNotFoundError:
        return "0.0.0+local"


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
unalias pip 2>/dev/null
unalias pip3 2>/dev/null
unalias npm 2>/dev/null
ig_wrap() {
  local bin="$1"
  shift
  case "$1" in
    install|i|add)
      command ig --no "$bin" "$@" || return $?
      ;;
  esac
  command "$bin" "$@"
}
pip()  { ig_wrap pip  "$@"; }
pip3() { ig_wrap pip3 "$@"; }
npm()  { ig_wrap npm  "$@"; }
"""


def take_flags(argv: list[str]) -> tuple[bool, bool | None, list[str]]:
    """Leading flags only. assume_yes: True=-y, False=--no, None=prompt if TTY."""
    force_json = False
    assume: bool | None = None
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag in {"--json", "-j"}:
            force_json = True
        elif flag in {"--yes", "-y"}:
            assume = True
        elif flag == "--no":
            assume = False
        else:
            break
        i += 1
    return force_json, assume, argv[i:]


def _req_file(line: str) -> str:
    handle, path = tempfile.mkstemp(prefix="ig-", suffix=".txt")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(line.strip() + "\n")
    return path


def _pypi_cmd(requirement: list[str], *, hashed: bool) -> list[str]:
    """uv venvs have no `python -m pip`. uv has no `--hash` flag; hashes go in a reqs file."""
    extra = ["--no-deps"] if hashed else []
    uv = shutil.which("uv")
    if uv:
        if hashed:
            path = _req_file(" ".join(requirement))
            return [
                uv,
                "pip",
                "install",
                "--python",
                sys.executable,
                "--no-deps",
                "--require-hashes",
                "-r",
                path,
            ]
        return [uv, "pip", "install", "--python", sys.executable, *extra, *requirement]
    pip = shutil.which("pip")
    if pip:
        return [pip, "install", *extra, *requirement]
    return [sys.executable, "-m", "pip", "install", *extra, *requirement]


def proposed_argv(verdict: GateVerdict) -> list[str] | None:
    """Pinned installer argv. Never the original unpinned line. None = do not run."""
    rem = verdict.remediation
    if rem is not None and rem.status == "VERIFIED_SUBSTITUTE" and rem.approved_requirement:
        if verdict.target.ecosystem is Ecosystem.PYPI:
            parts = shlex.split(rem.approved_requirement)
            return _pypi_cmd(parts, hashed=any(p.startswith("--hash=") for p in parts))
        return None
    if verdict.final_verdict is not Verdict.ALLOW or not verdict.target.version:
        return None
    target = verdict.target
    if target.ecosystem is Ecosystem.PYPI:
        req = [f"{target.name}=={target.version}"]
        hashed = bool(target.artifact_sha256)
        if hashed:
            req.append(f"--hash=sha256:{target.artifact_sha256}")
        return _pypi_cmd(req, hashed=hashed)
    if target.ecosystem is Ecosystem.NPM:
        npm = shutil.which("npm")
        if npm is None:
            return None
        return [npm, "install", f"{target.name}@{target.version}"]
    return None


def _req_path(argv: list[str]) -> str | None:
    if "-r" in argv:
        i = argv.index("-r")
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def _clip_hash(text: str) -> str:
    if text.startswith("--hash=sha256:") and len(text) > 27:
        return text[:27] + "…"
    return text


def _display(argv: list[str]) -> str:
    req = _req_path(argv)
    if req is not None:
        try:
            line = Path(req).read_text(encoding="utf-8").strip()
        except OSError:
            line = "pinned package"
        parts = [_clip_hash(p) for p in line.split()]
        return "uv pip install --no-deps " + " ".join(parts)
    shown: list[str] = []
    skip_next = False
    for part in argv:
        if skip_next:
            skip_next = False
            continue
        if part == "--python":
            skip_next = True
            continue
        if part == sys.executable:
            continue
        shown.append(_clip_hash(part))
    if shown[:3] == ["-m", "pip", "install"]:
        shown = ["pip", *shown[2:]]
    return " ".join(shown)


def confirm_run(display: str, *, default_yes: bool, assume: bool | None) -> bool:
    """apt/gh style. Empty enter uses the default. JSON/pipes never run unless -y."""
    if assume is True:
        return True
    if assume is False:
        return False
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    hint = "Y/n" if default_yes else "y/N"
    prompt = f"  ? Run `{display}` [{hint}] "
    try:
        print(prompt, end="", file=sys.stderr, flush=True)
        answer = input().strip().lower()
    except EOFError:
        return False
    if not answer:
        return default_yes
    return answer in {"y", "yes"}


def run(argv: list[str]) -> int:
    """Run one check from argv. Returns the process exit code."""
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(_HELP, end="")
        return 0 if argv else 2
    if argv[0] in {"-V", "--version", "version"}:
        print(f"installgate {package_version()}")
        return 0
    if argv[0] == "hook":
        print(hook_script(), end="")
        return 0
    force_json, assume, argv = take_flags(argv)
    pretty = sys.stdout.isatty() and not force_json
    try:
        command = command_from_argv(argv)
    except ValueError as exc:
        print(f"ig: {exc}", file=sys.stderr)
        print(_HELP, end="", file=sys.stderr)
        return 2
    started = time.perf_counter()
    on_stage = print_stage if pretty else None
    if pretty:
        print_header(command)
    verdict = asyncio.run(check(command, on_stage=on_stage))
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if pretty:
        print_verdict(verdict, command, elapsed_ms)
    else:
        print(verdict.model_dump_json(indent=2))
    code = exit_code(verdict.final_verdict)
    argv_run = proposed_argv(verdict)
    if argv_run is None:
        return code
    default_yes = verdict.final_verdict is Verdict.ALLOW
    req = _req_path(argv_run)
    try:
        if not confirm_run(_display(argv_run), default_yes=default_yes, assume=assume):
            if pretty:
                print("  skipped", file=sys.stderr)
            return code
        if pretty:
            print(f"  running {_display(argv_run)}", file=sys.stderr, flush=True)
        return subprocess.run(argv_run).returncode
    finally:
        if req:
            Path(req).unlink(missing_ok=True)


def main() -> None:
    """Load `.env` from the current directory, then run. Existing variables win."""
    load_env_file()
    raise SystemExit(run(sys.argv[1:]))
