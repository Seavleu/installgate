"""CLI argv: no `check`, no quotes. Does not call the network."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from contracts.contracts import Ecosystem, GateVerdict, TargetRef, Verdict
from mcp_server.cli import (
    command_from_argv,
    confirm_run,
    exit_code,
    hook_script,
    package_version,
    proposed_argv,
    run,
    take_flags,
)
from mcp_server.render import print_header, print_stage, print_verdict


def test_typed_install_line_needs_no_quotes() -> None:
    assert command_from_argv(["pip", "install", "reqeusts"]) == "pip install reqeusts"
    assert command_from_argv(["npm", "install", "lodash"]) == "npm install lodash"


def test_bare_name_is_pip_install() -> None:
    assert command_from_argv(["reqeusts"]) == "pip install reqeusts"
    assert command_from_argv(["requests==2.32.3"]) == "pip install requests==2.32.3"


def test_check_subcommand_still_works() -> None:
    assert command_from_argv(["check", "pip install requests"]) == "pip install requests"
    assert command_from_argv(["check", "pip", "install", "requests"]) == "pip install requests"


def test_exit_codes_match_verdict() -> None:
    assert exit_code(Verdict.ALLOW) == 0
    assert exit_code(Verdict.REVIEW) == 1
    assert exit_code(Verdict.BLOCK) == 2


def test_hook_wraps_pip_and_npm() -> None:
    text = hook_script()
    assert "command ig --no" in text
    assert "pip()" in text
    assert "npm()" in text
    assert "unalias pip" in text


def test_version_prints_the_package_and_does_not_check() -> None:
    assert run(["--version"]) == 0
    assert run(["-V"]) == 0
    assert run(["version"]) == 0


def test_package_version_is_nonempty() -> None:
    assert package_version()


def test_take_flags_strips_leading_only() -> None:
    json, assume, rest = take_flags(["-y", "pip", "install", "numpy"])
    assert json is False and assume is True and rest == ["pip", "install", "numpy"]
    json, assume, rest = take_flags(["--no", "--json", "reqeusts"])
    assert json is True and assume is False and rest == ["reqeusts"]


def _allow() -> GateVerdict:
    return GateVerdict(
        request_id="r1",
        target=TargetRef(
            ecosystem=Ecosystem.PYPI,
            name="numpy",
            version="2.5.4",
            artifact_sha256="a" * 64,
        ),
        policy_version="test",
        policy_verdict=Verdict.ALLOW,
        final_verdict=Verdict.ALLOW,
        outcome="ALLOW",  # type: ignore[arg-type]
        risk_score=0.0,
        evidence=[],
        next_action="proceed",
    )


def test_proposed_argv_installs_into_this_interpreter() -> None:
    argv = proposed_argv(_allow())
    assert argv is not None
    req = argv[argv.index("-r") + 1] if "-r" in argv else None
    try:
        assert "install" in argv
        line = Path(req).read_text(encoding="utf-8") if req else " ".join(argv)
        assert "numpy==2.5.4" in line
        assert "--hash=sha256:" in line
        assert "--no-deps" in argv
        if req:
            assert "--require-hashes" in argv
            assert "--hash=" not in " ".join(argv)
    finally:
        if req:
            Path(req).unlink(missing_ok=True)


def test_confirm_empty_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_server.cli.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("mcp_server.cli.sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: "")
    assert confirm_run("pip install numpy", default_yes=True, assume=None) is True
    assert confirm_run("pip install x", default_yes=False, assume=None) is False
    assert confirm_run("pip install x", default_yes=True, assume=False) is False
    assert confirm_run("pip install x", default_yes=False, assume=True) is True


def test_yes_execs_pip_and_does_not_import_the_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check(command: str, on_stage: object = None) -> GateVerdict:
        return _allow()

    ran: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> SimpleNamespace:
        text = ""
        if "-r" in argv:
            text = Path(argv[argv.index("-r") + 1]).read_text(encoding="utf-8")
        ran.append(argv + [text])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("mcp_server.cli.check", fake_check)
    monkeypatch.setattr("mcp_server.cli.subprocess.run", fake_run)
    monkeypatch.setattr("mcp_server.cli.sys.stdout.isatty", lambda: False)
    assert run(["-y", "pip", "install", "numpy"]) == 0
    assert ran and "install" in ran[0]
    assert any("numpy==2.5.4" in part for part in ran[0])


def test_no_flag_never_execs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_check(command: str, on_stage: object = None) -> GateVerdict:
        return _allow()

    monkeypatch.setattr("mcp_server.cli.check", fake_check)
    monkeypatch.setattr(
        "mcp_server.cli.subprocess.run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    monkeypatch.setattr("mcp_server.cli.sys.stdout.isatty", lambda: False)
    assert run(["--no", "pip", "install", "numpy"]) == 0


def test_stage_line_matches_the_ui(capsys: pytest.CaptureFixture[str]) -> None:
    print_stage({"stage": "parse", "status": "ok", "detail": "pypi · numpy · unpinned", "ms": 3})
    out = capsys.readouterr().out
    assert "Parse target" in out
    assert "pypi · numpy · unpinned" in out
    assert "3ms" in out


def test_header_is_cargo_checking(capsys: pytest.CaptureFixture[str]) -> None:
    print_header("pip install numpy")
    out = capsys.readouterr().out
    assert "Checking" in out
    assert "pip install numpy" in out


def test_allow_uses_uv_success_banner(capsys: pytest.CaptureFixture[str]) -> None:
    print_verdict(_allow(), "pip install numpy", 40)
    out = capsys.readouterr().out
    assert "success:" in out
    assert "ALLOW numpy==2.5.4" in out
    assert "help:" in out
    assert "note:" in out
