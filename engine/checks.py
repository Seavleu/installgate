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
# A reference set this small cannot support a typosquat claim either way. Rather
# than return "no match" — which reads as a clean bill of health — the check
# raises and the pipeline fails closed to REVIEW.
MIN_SNAPSHOT_NAMES = 100

_SNAPSHOTS = {
    Ecosystem.PYPI: "pypi-top5k-2026-10-25.txt",
    Ecosystem.NPM: "npm-top5k-2026-10-25.txt",
}

_SOURCE_FOR = {
    Ecosystem.PYPI: "pypi",
    Ecosystem.NPM: "npm",
    Ecosystem.HUGGINGFACE: "huggingface",
    Ecosystem.DOCKER: "docker_registry",
}


class SnapshotUnavailable(RuntimeError):
    """The typosquat reference set is missing or too small to decide anything."""


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
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return tuple(names)


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
        age_days = (now - first).days
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
        age_days = (now - latest).days
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
    if latest is None or (now - latest).days >= NEW_RELEASE_DAYS:
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


def check_osv_malicious(
    target: TargetRef, facts: dict[str, Any], builder: EvidenceBuilder
) -> Evidence | None:
    """P2: OSV holds a MAL- record. Hard, and the strongest signal we have."""
    if not facts.get("malicious"):
        return None
    return builder.build(
        EvidenceKind.OSV_MALICIOUS,
        source="osv",
        trust="deterministic",
        severity="hard",
        target=target,
        observed={"mal_ids": facts.get("mal_ids") or []},
        source_url="https://api.osv.dev/v1/query",
    )


def nearest_popular_name(name: str, ecosystem: Ecosystem) -> tuple[str, int] | None:
    """Closest name in the snapshot, if it is a near-miss rather than a match.

    Raises SnapshotUnavailable when the reference set is too small to be trusted —
    an empty answer there would be indistinguishable from "this name is fine".
    """
    candidate_names = load_top_names(ecosystem)
    if ecosystem in _SNAPSHOTS and len(candidate_names) < MIN_SNAPSHOT_NAMES:
        raise SnapshotUnavailable(
            f"{ecosystem.value} reference set has {len(candidate_names)} names, "
            f"fewer than the {MIN_SNAPSHOT_NAMES} required to judge a typosquat"
        )
    if not candidate_names:
        return None
    lowered = name.lower()
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


def check_typosquat(
    target: TargetRef,
    facts: dict[str, Any],
    builder: EvidenceBuilder,
    now: datetime | None = None,
) -> list[Evidence]:
    """P5 typosquat (soft), and P4 typosquat on a days-old project (hard, derived)."""
    match = nearest_popular_name(target.name, target.ecosystem)
    if match is None:
        return []
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
    if first is not None and (now - first).days < TYPOSQUAT_NEW_PROJECT_DAYS:
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
                    "age_days": (now - first).days,
                },
            )
        )
    return out


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
    unpatched runtime. The caller must turn that into REVIEW, never BLOCK.
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

    if not target.version:
        return RuntimeFloorResult(
            False, None, "digest-only reference: no tag to compare against a floor"
        )
    if not branches:
        return RuntimeFloorResult(False, None, f"no patched floors recorded for {image!r}")

    actual = _version_tuple(target.version)
    if actual is None:
        return RuntimeFloorResult(
            False, None, f"floating tag {target.version!r} carries no comparable version"
        )

    matched = _match_branch(actual, branches)
    if matched is None:
        return RuntimeFloorResult(
            False, None, f"{image} {target.version!r} is on a branch with no recorded floor"
        )

    branch, floor = matched
    required = _version_tuple(floor)
    if required is None:
        return RuntimeFloorResult(False, None, f"floor {floor!r} for branch {branch} is unusable")

    depth = min(len(actual), len(required))
    if actual[:depth] >= required[:depth]:
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
