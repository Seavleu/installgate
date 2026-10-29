"""CLI argv: no `check`, no quotes. Does not call the network."""

from __future__ import annotations

from contracts.contracts import Verdict
from mcp_server.cli import command_from_argv, exit_code, hook_script


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
    assert "command ig" in text
    assert "pip()" in text
    assert "npm()" in text
