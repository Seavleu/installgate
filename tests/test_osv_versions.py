"""A MAL- record is usually scoped to specific versions.

Matching on the package name alone hard-blocks every clean release of a project
that was compromised once. litellm carries MAL-2026-2144 for three releases out
of hundreds; that advisory must not stop `pip install litellm==1.80.0`.
"""

from __future__ import annotations

import pytest
from contracts.contracts import Ecosystem, EvidenceKind, TargetRef, Verdict
from engine import checks
from engine.clients.osv import affected_spec, summarise
from engine.evidence import EvidenceBuilder
from engine.policy import evaluate

# Shape taken verbatim from MAL-2026-2144 in ossf/malicious-packages.
LITELLM_RECORD = {
    "id": "MAL-2026-2144",
    "summary": "Malicious code in litellm (PyPI)",
    "affected": [
        {
            "package": {"name": "litellm", "ecosystem": "PyPI"},
            "versions": ["1.82.7", "1.82.8", "1.107.0"],
        }
    ],
}
WHOLE_PACKAGE_RECORD = {
    "id": "MAL-2024-0001",
    "affected": [{"package": {"name": "evilpkg", "ecosystem": "PyPI"}}],
}


def facts_for(*records: dict) -> dict:
    return summarise({"vulns": list(records)}, name="litellm")


def target(name: str, version: str | None = None) -> TargetRef:
    return TargetRef(ecosystem=Ecosystem.PYPI, name=name, version=version)


def test_affected_spec_reads_the_version_list():
    spec = affected_spec(LITELLM_RECORD, "litellm")
    assert spec["versions"] == ["1.107.0", "1.82.7", "1.82.8"]
    assert spec["whole_package"] is False


def test_affected_spec_marks_a_record_with_no_versions_as_whole_package():
    assert affected_spec(WHOLE_PACKAGE_RECORD, "evilpkg")["whole_package"] is True


@pytest.mark.parametrize("version", ["1.82.7", "1.82.8", "1.107.0"])
def test_an_affected_version_is_hard_evidence(version):
    evidence = checks.check_osv_malicious(
        target("litellm", version), facts_for(LITELLM_RECORD), EvidenceBuilder()
    )
    assert evidence is not None
    assert evidence.severity == "hard"
    assert evidence.observed["match"] == "version_covered"
    assert evidence.kind is EvidenceKind.OSV_MALICIOUS


@pytest.mark.parametrize("version", ["1.80.0", "1.82.6", "1.82.9", "1.108.0"])
def test_a_clean_version_of_the_same_package_is_not_flagged(version):
    assert (
        checks.check_osv_malicious(
            target("litellm", version), facts_for(LITELLM_RECORD), EvidenceBuilder()
        )
        is None
    )


def test_an_affected_version_blocks():
    facts = facts_for(LITELLM_RECORD)
    pinned = TargetRef(
        ecosystem=Ecosystem.PYPI, name="litellm", version="1.82.7", artifact_sha256="a" * 64
    )
    evidence = checks.check_osv_malicious(pinned, facts, EvidenceBuilder())
    assert evaluate(pinned, [evidence]).verdict is Verdict.BLOCK


def test_a_clean_version_is_not_blocked_by_p2():
    facts = facts_for(LITELLM_RECORD)
    pinned = TargetRef(
        ecosystem=Ecosystem.PYPI, name="litellm", version="1.80.0", artifact_sha256="a" * 64
    )
    assert checks.check_osv_malicious(pinned, facts, EvidenceBuilder()) is None
    assert evaluate(pinned, []).verdict is Verdict.ALLOW


def test_an_unpinned_install_is_undetermined_and_reviews_rather_than_blocks():
    # Nothing is pinned, so we cannot say which release would be fetched. That
    # is not grounds for a BLOCK, and it is certainly not grounds for an ALLOW.
    unpinned = target("litellm")
    evidence = checks.check_osv_malicious(unpinned, facts_for(LITELLM_RECORD), EvidenceBuilder())
    assert evidence is not None
    assert evidence.severity == "soft"
    assert evidence.observed["match"] == "version_undetermined"
    assert evaluate(unpinned, [evidence]).verdict is Verdict.REVIEW


def test_a_whole_package_record_still_blocks_by_name():
    facts = summarise({"vulns": [WHOLE_PACKAGE_RECORD]}, name="evilpkg")
    pinned = TargetRef(
        ecosystem=Ecosystem.PYPI, name="evilpkg", version="9.9.9", artifact_sha256="a" * 64
    )
    evidence = checks.check_osv_malicious(pinned, facts, EvidenceBuilder())
    assert evidence is not None
    assert evidence.severity == "hard"
    assert evaluate(pinned, [evidence]).verdict is Verdict.BLOCK


def test_an_open_ended_range_covers_everything_after_its_start():
    ranged = {
        "id": "MAL-2025-9999",
        "affected": [
            {
                "package": {"name": "litellm", "ecosystem": "PyPI"},
                "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "1.0.0"}]}],
            }
        ],
    }
    facts = facts_for(ranged)
    # No fix was ever published, so 2.0.0 is still affected.
    after = checks.check_osv_malicious(target("litellm", "2.0.0"), facts, EvidenceBuilder())
    assert after is not None and after.severity == "hard"
    # A release from before the range starts is not.
    assert checks.check_osv_malicious(target("litellm", "0.9"), facts, EvidenceBuilder()) is None


def test_version_comparison_is_pep440_not_string_equality():
    record = {
        "id": "MAL-2025-0002",
        "affected": [{"package": {"name": "litellm", "ecosystem": "PyPI"}, "versions": ["1.0"]}],
    }
    facts = facts_for(record)
    assert checks.check_osv_malicious(target("litellm", "1.0.0"), facts, EvidenceBuilder())
    # 1.82.70 is not 1.82.7, which plain prefix matching would confuse.
    assert (
        checks.check_osv_malicious(
            target("litellm", "1.82.70"), facts_for(LITELLM_RECORD), EvidenceBuilder()
        )
        is None
    )


def test_legacy_facts_without_version_detail_still_block():
    # A cached or hand-written fixture that predates mal_records.
    legacy = {"malicious": True, "mal_ids": ["MAL-2020-0001"]}
    pinned = TargetRef(
        ecosystem=Ecosystem.PYPI, name="old", version="1.0.0", artifact_sha256="a" * 64
    )
    evidence = checks.check_osv_malicious(pinned, legacy, EvidenceBuilder())
    assert evidence is not None
    assert evidence.severity == "hard"


# ---------- ranges ----------
def ranged_record(events: list[dict], rid: str = "MAL-2025-7777") -> dict:
    return {
        "id": rid,
        "affected": [
            {
                "package": {"name": "litellm", "ecosystem": "PyPI"},
                "ranges": [{"type": "ECOSYSTEM", "events": events}],
            }
        ],
    }


def test_introduced_zero_with_no_fix_covers_every_version():
    """The common shape for a malicious package: bad from its first release.

    22 of the 50 advisories in the benchmark look exactly like this. Treating
    them as undecidable downgrades a real BLOCK to REVIEW.
    """
    facts = facts_for(ranged_record([{"introduced": "0"}]))
    for version in ("0.0.1", "1.0.0", "99.9"):
        evidence = checks.check_osv_malicious(target("litellm", version), facts, EvidenceBuilder())
        assert evidence is not None and evidence.severity == "hard", version


def test_introduced_zero_covers_an_unpinned_install_too():
    # No comparison is needed when every version is affected.
    evidence = checks.check_osv_malicious(
        target("litellm"), facts_for(ranged_record([{"introduced": "0"}])), EvidenceBuilder()
    )
    assert evidence is not None
    assert evidence.severity == "hard"


def test_a_fixed_event_excludes_later_versions():
    facts = facts_for(ranged_record([{"introduced": "1.0.0"}, {"fixed": "2.0.0"}]))
    assert checks.check_osv_malicious(target("litellm", "1.5.0"), facts, EvidenceBuilder())
    assert checks.check_osv_malicious(target("litellm", "2.0.0"), facts, EvidenceBuilder()) is None
    assert checks.check_osv_malicious(target("litellm", "0.9.0"), facts, EvidenceBuilder()) is None


def test_last_affected_is_inclusive_unlike_fixed():
    facts = facts_for(ranged_record([{"introduced": "1.0.0"}, {"last_affected": "2.0.0"}]))
    assert checks.check_osv_malicious(target("litellm", "2.0.0"), facts, EvidenceBuilder())
    assert checks.check_osv_malicious(target("litellm", "2.0.1"), facts, EvidenceBuilder()) is None


def test_a_bounded_range_is_undetermined_when_nothing_is_pinned():
    facts = facts_for(ranged_record([{"introduced": "1.0.0"}, {"fixed": "2.0.0"}]))
    evidence = checks.check_osv_malicious(target("litellm"), facts, EvidenceBuilder())
    assert evidence is not None
    assert evidence.severity == "soft"
