"""Stage 1 checks. Pure functions: facts in, Evidence out. They never fetch."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from contracts.contracts import Ecosystem, Evidence, EvidenceKind, TargetRef
from rapidfuzz.distance import DamerauLevenshtein

from engine.evidence import EvidenceBuilder

DATA_DIR = Path(__file__).parent / "data"
FLOORS_PATH = Path(__file__).parent / "runtime_floors.yaml"

NEW_PROJECT_DAYS = 30
NEW_RELEASE_DAYS = 30
TYPOSQUAT_NEW_PROJECT_DAYS = 7
TYPOSQUAT_MAX_DISTANCE = 2
# Below this length a 1-edit distance is normal between unrelated names.
TYPOSQUAT_MIN_LENGTH = 5
# Minimum reference names an ecosystem needs before a near-miss means anything,
# per ecosystem. `None` disables the check for that ecosystem outright.
#
# A snapshot smaller than its threshold is a misconfiguration, not a coverage
# decision: the file was meant to be there and is short, so the check raises and
# the pipeline fails closed. A `None` is a deliberate "we do not cover this yet".
MIN_SNAPSHOT_NAMES: dict[Ecosystem, int | None] = {
    # A real top-5000 snapshot is in place (see the file header for its source
    # and date). The bar sits just below it so a truncated or half-written file
    # fails the check instead of quietly shrinking its coverage.
    Ecosystem.PYPI: 4000,
    # Cut from this milestone: no vetted popular-name source for npm, so the
    # check is off rather than running against 226 names written from memory.
    Ecosystem.NPM: None,
}

# Ecosystems the typosquat check applies to at all. Container images and model
# repositories are namespaced, so a flat popular-name list is the wrong tool.
TYPOSQUAT_ECOSYSTEMS = frozenset({Ecosystem.PYPI, Ecosystem.NPM})

# Dated snapshots, fetched by eval/fetch_top_pypi.py. npm has no entry: the
# check is switched off for it, so there is nothing to point at.
_SNAPSHOTS = {
    Ecosystem.PYPI: "pypi-top5000-2026-10-27.txt",
}

_SOURCE_FOR = {
    Ecosystem.PYPI: "pypi",
    Ecosystem.NPM: "npm",
    Ecosystem.HUGGINGFACE: "huggingface",
    Ecosystem.DOCKER: "docker_registry",
}


class SnapshotUnavailable(RuntimeError):
    """The typosquat reference set is missing or too small to decide anything."""


_PEP503_SEPARATORS = re.compile(r"[-_.]+")


def normalize_name(name: str, ecosystem: Ecosystem) -> str:
    """PEP 503 normalisation for PyPI, plain lowercase elsewhere.

    `Requests_OAuthlib` and `requests-oauthlib` are the same project to PyPI, so
    comparing them unnormalised reports a two-edit "typosquat" of a package
    against itself.
    """
    lowered = name.strip().lower()
    if ecosystem is Ecosystem.PYPI:
        return _PEP503_SEPARATORS.sub("-", lowered)
    return lowered


def _parse_iso(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


@functools.lru_cache(maxsize=4)
def load_top_names(ecosystem: Ecosystem) -> tuple[str, ...]:
    """Dated top-5k snapshot used as the typosquat reference set."""
    filename = _SNAPSHOTS.get(ecosystem)
    if filename is None:
        return ()
    path = DATA_DIR / filename
    if not path.exists():
        return ()
    names = [
        normalize_name(line, ecosystem)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    # Normalisation collapses spellings, so dedupe while keeping file order.
    return tuple(dict.fromkeys(names))


@functools.lru_cache(maxsize=1)
def load_runtime_floors() -> dict[str, dict[str, str]]:
    """Image -> release branch -> patched floor.

    A single floor per image cannot describe a project that patches several
    branches at once, so floors are keyed by branch (`"8.2"`, `"20"`).
    """
    if not FLOORS_PATH.exists():
        return {}
    data = yaml.safe_load(FLOORS_PATH.read_text(encoding="utf-8")) or {}
    images = data.get("images") or {}
    out: dict[str, dict[str, str]] = {}
    for image, spec in images.items():
        branches = (spec or {}).get("branches") or {}
        out[str(image)] = {str(b): str(f) for b, f in branches.items()}
    return out


def _check_unavailable(
    builder: EvidenceBuilder, target: TargetRef, reason: str, detail: str, **extra: Any
) -> Evidence:
    """Soft evidence that a check could not run, so a silent gap cannot read as clean.

    `reason` must be one of CHECK_UNAVAILABLE_REASONS; the contract enforces it.
    The records come from our own tables (policy_yaml), not from a registry.
    """
    return builder.build(
        EvidenceKind.CHECK_UNAVAILABLE,
        source="policy_yaml",
        trust="deterministic",
        severity="soft",
        target=target,
        observed={"reason": reason, "detail": detail, **extra},
    )


def check_exists(
    target: TargetRef, facts: dict[str, Any], builder: EvidenceBuilder
) -> Evidence | None:
    """P1: the package does not exist. Hard — a hallucinated name can be squatted tomorrow."""
    if facts.get("exists"):
        return None
    return builder.build(
        EvidenceKind.NOT_FOUND,
        source=_SOURCE_FOR[target.ecosystem],  # type: ignore[arg-type]
        trust="deterministic",
        severity="hard",
        target=target,
        observed={"name": target.name, "ecosystem": target.ecosystem.value},
    )


def check_age(
    target: TargetRef,
    facts: dict[str, Any],
    builder: EvidenceBuilder,
    now: datetime | None = None,
) -> list[Evidence]:
    """P6: a very new project or a very new release. Soft — age alone never blocks."""
    if not facts.get("exists"):
        return []
    now = now or datetime.now(UTC)
    out: list[Evidence] = []
    source = _SOURCE_FOR[target.ecosystem]

    first = _parse_iso(facts.get("first_upload"))
    if first is not None:
        # A release dated after the clock means the clock is stale, not that the
        # package is from the future. Clamp, or a negative age silently satisfies
        # every "younger than N days" test.
        age_days = max((now - first).days, 0)
        if age_days < NEW_PROJECT_DAYS:
            out.append(
                builder.build(
                    EvidenceKind.NEW_PROJECT,
                    source=source,  # type: ignore[arg-type]
                    trust="deterministic",
                    severity="soft",
                    target=target,
                    observed={"first_upload": first.isoformat(), "age_days": age_days},
                )
            )

    latest = _parse_iso(facts.get("latest_upload"))
    if latest is not None:
        age_days = max((now - latest).days, 0)
        if age_days < NEW_RELEASE_DAYS:
            out.append(
                builder.build(
                    EvidenceKind.NEW_RELEASE,
                    source=source,  # type: ignore[arg-type]
                    trust="deterministic",
                    severity="soft",
                    target=target,
                    observed={
                        "latest_upload": latest.isoformat(),
                        "age_days": age_days,
                        "latest_version": facts.get("latest_version"),
                    },
                )
            )
    return out


def check_maintainers(
    target: TargetRef,
    facts: dict[str, Any],
    builder: EvidenceBuilder,
    known_maintainers: list[str] | None = None,
    now: datetime | None = None,
) -> Evidence | None:
    """P8: the maintainer set changed and a release followed soon after.

    `known_maintainers` is the previously cached set. With no prior snapshot there is
    nothing to compare against, so this check stays silent rather than guessing.
    """
    if not facts.get("exists") or known_maintainers is None:
        return None
    current = set(facts.get("maintainers") or [])
    previous = set(known_maintainers)
    if not previous or current == previous:
        return None

    now = now or datetime.now(UTC)
    latest = _parse_iso(facts.get("latest_upload"))
    if latest is None or max((now - latest).days, 0) >= NEW_RELEASE_DAYS:
        return None

    return builder.build(
        EvidenceKind.MAINTAINER_CHANGE,
        source=_SOURCE_FOR[target.ecosystem],  # type: ignore[arg-type]
        trust="deterministic",
        severity="soft",
        target=target,
        observed={
            "added": sorted(current - previous),
            "removed": sorted(previous - current),
            "latest_upload": latest.isoformat(),
        },
    )


def _same_version(left: str, right: str) -> bool:
    """Compare two versions, tolerating `1.0` against `1.0.0` where possible."""
    try:
        from packaging.version import InvalidVersion, Version
    except ImportError:  # pragma: no cover - packaging ships with the toolchain
        return left.strip() == right.strip()
    try:
        return Version(left) == Version(right)
    except InvalidVersion:
        return left.strip() == right.strip()


def _parse_version(raw: str) -> Any | None:
    try:
        from packaging.version import InvalidVersion, Version
    except ImportError:  # pragma: no cover - packaging ships with the toolchain
        return None
    try:
        return Version(raw)
    except InvalidVersion:
        return None


# Range event keys we know how to read on a version-ordered range.
_KNOWN_EVENTS = frozenset({"introduced", "fixed", "last_affected"})


def _range_covers(rng: dict[str, Any], version: str | None) -> bool | None:
    """Evaluate one OSV range against a version.

    The overwhelmingly common shape for a malicious package is a single
    `introduced: "0"` with no fix: the project was malicious from its first
    release, so every version is covered and no comparison is needed. Treating
    that as undecided downgrades a real BLOCK to REVIEW.
    """
    events = rng.get("events") or []

    # A GIT range is ordered by commit, not by version. Mapping one to a release
    # needs the repository, which we do not read, so there is nothing to compare
    # and the answer is "cannot tell" rather than a guess in either direction.
    if str(rng.get("type", "")).upper() == "GIT":
        return None

    # `limit` bounds a GIT traversal and has no version meaning on an
    # ECOSYSTEM or SEMVER range. Seeing one here means the record is shaped in
    # a way this code was not written for; say so instead of ignoring it.
    if any(key not in _KNOWN_EVENTS for event in events for key in event):
        return None

    introduced = [str(e["introduced"]) for e in events if "introduced" in e]
    closing = [
        str(e.get("fixed") or e.get("last_affected"))
        for e in events
        if "fixed" in e or "last_affected" in e
    ]

    if not closing and "0" in introduced:
        return True
    if version is None:
        return None

    current = _parse_version(version)
    if current is None:
        return None

    # Pair each introduced with the next closing event, in order.
    lower = _parse_version(introduced[0]) if introduced and introduced[0] != "0" else None
    if introduced and introduced[0] != "0" and lower is None:
        return None
    if lower is not None and bool(current < lower):
        return False
    if not closing:
        return True

    upper_raw = closing[0]
    upper = _parse_version(upper_raw)
    if upper is None:
        return None
    is_fixed = any("fixed" in e for e in events)
    return bool(current < upper) if is_fixed else bool(current <= upper)


def record_covers(record: dict[str, Any], version: str | None) -> bool | None:
    """Does this advisory cover `version`? None when it cannot be decided.

    True  - the record names this version, covers the whole project, or has a
            range open from the first release.
    False - the record scopes itself and this release falls outside.
    None  - the version is unknown, or a range we cannot order. Undecided must
            never read as clean.
    """
    if record.get("whole_package"):
        return True

    versions = [str(v) for v in (record.get("versions") or [])]
    if version is not None and versions and any(_same_version(version, v) for v in versions):
        return True

    verdicts = [_range_covers(r, version) for r in (record.get("ranges") or [])]
    if any(v is True for v in verdicts):
        return True
    if any(v is None for v in verdicts):
        return None

    if version is None:
        return None
    if versions or verdicts:
        return False
    return None


def check_osv_malicious(
    target: TargetRef, facts: dict[str, Any], builder: EvidenceBuilder
) -> Evidence | None:
    """P2: OSV holds a MAL- record covering this release.

    A MAL- record is usually scoped to particular versions. `litellm` carries
    MAL-2026-2144 for three releases out of hundreds, so matching on the name
    alone would hard-block every clean version of a widely used package.

    Severity carries how certain the match is, and the policy turns an
    uncertain one into REVIEW rather than BLOCK:
      hard - the record covers this exact version, or the whole project
      soft - a record exists for the name but this install cannot be placed in
             it: nothing is pinned yet, or the record uses version ranges
      none - the record names versions and this release is not among them
    """
    if not facts.get("malicious"):
        return None

    records = facts.get("mal_records")
    if not records:
        # Facts from an older cache or a hand-written fixture carry no version
        # detail, so a name match is the whole of what we know.
        records = [{"id": i, "whole_package": True} for i in (facts.get("mal_ids") or [])]

    verdicts = [(r, record_covers(r, target.version)) for r in records]
    covering = [r for r, covered in verdicts if covered is True]
    undecided = [r for r, covered in verdicts if covered is None]

    matched = covering or undecided
    if not matched:
        return None

    return builder.build(
        EvidenceKind.OSV_MALICIOUS,
        source="osv",
        trust="deterministic",
        severity="hard" if covering else "soft",
        target=target,
        observed={
            "mal_ids": sorted(str(r.get("id")) for r in matched),
            "version_checked": target.version,
            "affected_versions": sorted(
                {str(v) for r in matched for v in (r.get("versions") or [])}
            ),
            "match": "version_covered" if covering else "version_undetermined",
        },
        source_url="https://api.osv.dev/v1/query",
    )


def typosquat_coverage(ecosystem: Ecosystem) -> str | None:
    """Why this ecosystem has no typosquat coverage, or None when it needs none.

    Only name-based package registries are in scope. A container image or a
    model repository is addressed by `namespace/name`, and a near-miss there is
    a different problem with different reference data — so the check is not
    applicable rather than missing, and must not hold back an ALLOW.
    """
    if ecosystem not in TYPOSQUAT_ECOSYSTEMS:
        return None
    if MIN_SNAPSHOT_NAMES.get(ecosystem) is None:
        return (
            f"typosquat check is disabled for {ecosystem.value}: no vetted "
            "popular-name source for this milestone"
        )
    if ecosystem not in _SNAPSHOTS:
        return f"no popular-name reference set exists for {ecosystem.value}"
    return None


def nearest_popular_name(name: str, ecosystem: Ecosystem) -> tuple[str, int] | None:
    """Closest name in the snapshot, if it is a near-miss rather than a match.

    Raises SnapshotUnavailable when a snapshot that should be there is too short
    to be trusted — an empty answer would be indistinguishable from "name is fine".
    An ecosystem with the check switched off is handled by `typosquat_coverage`
    before this is called.
    """
    threshold = MIN_SNAPSHOT_NAMES.get(ecosystem)
    candidate_names = load_top_names(ecosystem)
    if threshold is not None and len(candidate_names) < threshold:
        raise SnapshotUnavailable(
            f"{ecosystem.value} reference set has {len(candidate_names)} names, "
            f"fewer than the {threshold} required to judge a typosquat"
        )
    if not candidate_names:
        return None
    lowered = normalize_name(name, ecosystem)
    if lowered in candidate_names or len(lowered) < TYPOSQUAT_MIN_LENGTH:
        return None

    best: tuple[str, int] | None = None
    for popular in candidate_names:
        if abs(len(popular) - len(lowered)) > TYPOSQUAT_MAX_DISTANCE:
            continue
        distance = DamerauLevenshtein.distance(
            lowered, popular, score_cutoff=TYPOSQUAT_MAX_DISTANCE
        )
        if distance == 0 or distance > TYPOSQUAT_MAX_DISTANCE:
            continue
        if best is None or distance < best[1]:
            best = (popular, distance)
            if distance == 1:
                break
    return best


@dataclass(frozen=True)
class TyposquatResult:
    """Outcome of the near-miss check.

    `covered` is False when the ecosystem has no usable reference set. As with
    the runtime floors, that is an absence of knowledge: it must not read as a
    clean result, so `evidence` carries a soft check_unavailable record (P10
    turns it into REVIEW) and never a BLOCK.
    """

    covered: bool
    evidence: list[Evidence]
    reason: str | None = None


def check_typosquat(
    target: TargetRef,
    facts: dict[str, Any],
    builder: EvidenceBuilder,
    now: datetime | None = None,
) -> TyposquatResult:
    """P5 typosquat (soft), and P4 typosquat on a days-old project (hard, derived)."""
    uncovered = typosquat_coverage(target.ecosystem)
    if uncovered is not None:
        unavailable = _check_unavailable(
            builder, target, "typosquat_unsupported_ecosystem", uncovered
        )
        return TyposquatResult(covered=False, evidence=[unavailable], reason=uncovered)

    match = nearest_popular_name(target.name, target.ecosystem)
    if match is None:
        return TyposquatResult(covered=True, evidence=[])
    popular, distance = match
    source = _SOURCE_FOR[target.ecosystem]
    observed = {
        "candidate": target.name,
        "nearest_popular": popular,
        "distance": distance,
        "snapshot": _SNAPSHOTS.get(target.ecosystem),
    }

    out = [
        builder.build(
            EvidenceKind.TYPOSQUAT,
            source=source,  # type: ignore[arg-type]
            trust="deterministic",
            severity="soft",
            target=target,
            observed=observed,
        )
    ]

    now = now or datetime.now(UTC)
    first = _parse_iso(facts.get("first_upload"))
    if first is not None and max((now - first).days, 0) < TYPOSQUAT_NEW_PROJECT_DAYS:
        out.append(
            builder.build(
                EvidenceKind.TYPOSQUAT_NEW_PROJECT,
                source=source,  # type: ignore[arg-type]
                trust="deterministic",
                severity="hard",
                target=target,
                observed={
                    **observed,
                    "first_upload": first.isoformat(),
                    "age_days": max((now - first).days, 0),
                },
            )
        )
    return TyposquatResult(covered=True, evidence=out)


def check_hf_format(
    target: TargetRef, facts: dict[str, Any], builder: EvidenceBuilder
) -> list[Evidence]:
    """P7: pickle weights with no safetensors sibling. Loading a pickle executes code."""
    if not facts.get("exists") or not facts.get("has_pickle"):
        return []

    out = [
        builder.build(
            EvidenceKind.HF_PICKLE,
            source="huggingface",
            trust="deterministic",
            severity="soft",
            target=target,
            observed={"pickle_files": facts.get("pickle_files") or []},
            source_url=f"https://huggingface.co/{target.name}",
        )
    ]
    if facts.get("has_safetensors"):
        out.append(
            builder.build(
                EvidenceKind.HF_SAFETENSORS_SIBLING,
                source="huggingface",
                trust="deterministic",
                severity="info",
                target=target,
                observed={"safetensors_files": facts.get("safetensors_files") or []},
                source_url=f"https://huggingface.co/{target.name}",
            )
        )
    return out


_VERSION_PART = re.compile(r"\d+")


def _version_tuple(version: str) -> tuple[int, ...] | None:
    """Numeric prefix of a tag. `3.11.9-slim` -> (3, 11, 9). Non-numeric tags -> None."""
    head = version.split("-")[0]
    parts = head.split(".")
    if not parts or not _VERSION_PART.fullmatch(parts[0]):
        return None
    numbers: list[int] = []
    for part in parts:
        if not _VERSION_PART.fullmatch(part):
            break
        numbers.append(int(part))
    return tuple(numbers) or None


@dataclass(frozen=True)
class RuntimeFloorResult:
    """Outcome of the base-tag check.

    `comparable` is the half that matters for FR-09: when we cannot place a tag
    on a known release branch we have an absence of knowledge, not evidence of an
    unpatched runtime. `evidence` is then a soft check_unavailable record, which
    P10 turns into REVIEW, never BLOCK.
    """

    comparable: bool
    evidence: Evidence | None
    reason: str
    branch: str | None = None
    floor: str | None = None


def _match_branch(tag: tuple[int, ...], branches: dict[str, str]) -> tuple[str, str] | None:
    """Longest branch whose version tuple prefixes the tag. `8.2.20` -> branch `8.2`."""
    best: tuple[str, str] | None = None
    best_len = -1
    for branch, floor in branches.items():
        prefix = _version_tuple(branch)
        if prefix is None or len(prefix) > len(tag):
            continue
        if tag[: len(prefix)] == prefix and len(prefix) > best_len:
            best, best_len = (branch, floor), len(prefix)
    return best


def check_runtime_floor(
    target: TargetRef,
    builder: EvidenceBuilder,
    floors: dict[str, dict[str, str]] | None = None,
) -> RuntimeFloorResult:
    """P3: a Dockerfile base tag below the patched floor of its own release branch.

    BLOCK is reserved for a tag we can place on a known branch and show to be
    behind that branch's floor. Everything else — an image we hold no floors for,
    a branch not in the table, a floating tag (`latest`, `bookworm`), or a
    digest-only reference with no tag — is not comparable and resolves to REVIEW
    (FR-09).
    """
    if target.ecosystem != Ecosystem.DOCKER:
        return RuntimeFloorResult(True, None, "not a container image")

    floors = floors if floors is not None else load_runtime_floors()
    image = target.name.rsplit("/", 1)[-1].lower()
    branches = floors.get(image)

    def unavailable(code: str, detail: str) -> RuntimeFloorResult:
        record = _check_unavailable(builder, target, code, detail, image=image, tag=target.version)
        return RuntimeFloorResult(False, record, detail)

    if not target.version:
        return unavailable(
            "digest_only", "digest-only reference: no tag to compare against a floor"
        )
    if not branches:
        return unavailable("image_not_in_table", f"no patched floors recorded for {image!r}")

    actual = _version_tuple(target.version)
    if actual is None:
        return unavailable(
            "floating_tag", f"floating tag {target.version!r} carries no comparable version"
        )

    matched = _match_branch(actual, branches)
    if matched is None:
        return unavailable(
            "no_floor_for_branch",
            f"{image} {target.version!r} is on a branch with no recorded floor",
        )

    branch, floor = matched
    required = _version_tuple(floor)
    if required is None:
        return unavailable(
            "no_floor_for_branch", f"floor {floor!r} for branch {branch} is unusable"
        )

    depth = min(len(actual), len(required))
    if actual[:depth] >= required[:depth]:
        if len(actual) < len(required):
            # `8.3` or `8.3-apache` floats to whatever patch the registry serves
            # today, so it cannot be shown to be at or above the floor.
            return unavailable(
                "floating_tag", f"tag {target.version!r} does not pin a patch release"
            )
        return RuntimeFloorResult(True, None, "at or above the branch floor", branch, floor)

    evidence = builder.build(
        EvidenceKind.RUNTIME_BELOW_FLOOR,
        source="docker_registry",
        trust="deterministic",
        severity="hard",
        target=target,
        observed={
            "image": image,
            "tag": target.version,
            "branch": branch,
            "patched_floor": floor,
        },
    )
    return RuntimeFloorResult(True, evidence, "below the branch floor", branch, floor)
