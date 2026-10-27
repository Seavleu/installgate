"""Command diff. The safe line is shown. It is never run."""

from __future__ import annotations


def command_diff(bad: str, safe: str) -> str:
    return f"- {bad}\n+ {safe}"


def safe_command(original_command: str, bad_token: str, requirement: str) -> str:
    if bad_token and bad_token in original_command:
        return original_command.replace(bad_token, requirement, 1)
    return requirement
