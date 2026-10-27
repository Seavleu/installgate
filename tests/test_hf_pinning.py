"""Hugging Face is pinned by git revision, filled from the API's model sha (T22)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from contracts.contracts import Ecosystem, TargetRef, Verdict
from engine import stage1
from engine.parsers import parse_hf_repo_id
from engine.policy import is_pinned

NOW = datetime(2026, 10, 28, tzinfo=UTC)
SHA = "c" * 40


def hf_facts(**over: Any) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "exists": True,
        "files": ["model.safetensors", "config.json"],
        "pickle_files": [],
        "safetensors_files": ["model.safetensors"],
        "has_pickle": False,
        "has_safetensors": True,
        "first_upload": "2023-01-01T00:00:00+00:00",
        "latest_upload": "2024-01-01T00:00:00+00:00",
        "sha": SHA,
    }
    facts.update(over)
    return facts


def repo(revision: str | None = None) -> TargetRef:
    return TargetRef(ecosystem=Ecosystem.HUGGINGFACE, name="org/model", revision=revision)


def test_is_pinned_follows_the_contract() -> None:
    assert is_pinned(repo(SHA))
    assert not is_pinned(repo())
    assert not is_pinned(TargetRef(ecosystem=Ecosystem.PYPI, name="requests", revision=SHA))
    assert is_pinned(
        TargetRef(ecosystem=Ecosystem.PYPI, name="r", version="1", artifact_sha256="a" * 64)
    )


def test_safetensors_repo_gets_its_revision_from_the_api_and_is_allowed() -> None:
    result = stage1.run(repo(), hf_facts(), now=NOW)
    assert result.target.revision == SHA
    assert result.verdict is Verdict.ALLOW
    assert result.decision.matched_rules == ("P9",)
    assert result.evidence == []


def test_a_revision_the_caller_pinned_is_kept() -> None:
    mine = "d" * 40
    result = stage1.run(repo(mine), hf_facts(), now=NOW)
    assert result.target.revision == mine
    assert result.verdict is Verdict.ALLOW


def test_pickle_only_repo_is_review_by_p7() -> None:
    facts = hf_facts(
        files=["pytorch_model.bin"],
        pickle_files=["pytorch_model.bin"],
        safetensors_files=[],
        has_pickle=True,
        has_safetensors=False,
    )
    result = stage1.run(repo(), facts, now=NOW)
    assert result.verdict is Verdict.REVIEW
    assert "P7" in result.decision.matched_rules


def test_no_api_sha_means_review_never_allow() -> None:
    for facts in (hf_facts(sha=None), {k: v for k, v in hf_facts().items() if k != "sha"}):
        result = stage1.run(repo(), facts, now=NOW)
        assert result.target.revision is None
        assert result.verdict is Verdict.REVIEW


def test_a_malformed_api_sha_is_not_a_pin() -> None:
    for bad in ("main", "C" * 40, "c" * 64, 12345):
        result = stage1.run(repo(), hf_facts(sha=bad), now=NOW)
        assert result.target.revision is None
        assert result.verdict is Verdict.REVIEW


def test_a_missing_repo_still_blocks() -> None:
    result = stage1.run(repo(), {"exists": False}, now=NOW)
    assert result.verdict is Verdict.BLOCK


def test_parsed_hf_target_flows_through() -> None:
    ref = parse_hf_repo_id("org/model")
    assert stage1.run(ref, hf_facts(), now=NOW).verdict is Verdict.ALLOW
