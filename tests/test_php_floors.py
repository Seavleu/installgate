"""The php floors in runtime_floors.yaml, exercised through Stage 1 (T23)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from contracts.contracts import Ecosystem, EvidenceKind, TargetRef, Verdict
from engine import checks, stage1

NOW = datetime(2026, 10, 28, tzinfo=UTC)
FLOORS_FILE = Path(__file__).parent.parent / "engine" / "runtime_floors.yaml"


def php(tag: str) -> stage1.Stage1Result:
    ref = TargetRef(ecosystem=Ecosystem.DOCKER, name="php", version=tag, artifact_sha256="d" * 64)
    return stage1.run(ref, {"exists": True}, now=NOW)


def test_php_floors_are_the_advisory_values() -> None:
    assert checks.load_runtime_floors()["php"] == {
        "8.2": "8.2.35",
        "8.3": "8.3.36",
        "8.4": "8.4.27",
        "8.5": "8.5.12",
    }


def test_one_below_the_floor_blocks_on_p3() -> None:
    result = php("8.3.35")
    assert result.verdict is Verdict.BLOCK
    assert "P3" in result.decision.matched_rules
    assert [e.kind for e in result.evidence] == [EvidenceKind.RUNTIME_BELOW_FLOOR]
    assert result.evidence[0].severity == "hard"


def test_the_floor_itself_is_allowed() -> None:
    result = php("8.3.36")
    assert result.verdict is Verdict.ALLOW
    assert result.evidence == []


@pytest.mark.parametrize("tag", ["8.2.34", "8.4.26", "8.5.11"])
def test_every_listed_branch_blocks_below_its_own_floor(tag: str) -> None:
    assert php(tag).verdict is Verdict.BLOCK


@pytest.mark.parametrize("tag", ["8.2.35", "8.4.27", "8.5.12"])
def test_every_listed_branch_allows_at_its_floor(tag: str) -> None:
    assert php(tag).verdict is Verdict.ALLOW


@pytest.mark.parametrize("tag", ["8.1.30", "8.0.30", "7.4.33"])
def test_branches_without_a_floor_are_review_never_block(tag: str) -> None:
    result = php(tag)
    assert result.verdict is Verdict.REVIEW
    assert [e.observed["reason"] for e in result.evidence] == ["no_floor_for_branch"]


def test_only_php_is_marked_verified() -> None:
    data = yaml.safe_load(FLOORS_FILE.read_text(encoding="utf-8"))
    assert data["images"]["php"]["verified"] is True
    assert data["images"]["php"]["source"] == "https://www.php.net/archive/2026.php"
    for name, spec in data["images"].items():
        if name != "php":
            assert "verified" not in spec, f"{name} must stay unverified"
    assert data["verified"] is False
