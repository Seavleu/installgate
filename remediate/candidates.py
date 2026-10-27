"""Closed substitute set (T10). The model may pick a candidate by id only."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from contracts.contracts import SafeRemediation, TargetRef

from remediate.diff import command_diff, safe_command
from remediate.pinning import approved_requirement, pinned

Source = Literal["alias_map", "top_n_neighbor", "hf_sibling", "docker_patched_floor"]
_ID = re.compile(r"^C[1-9][0-9]*$")
# Spec example only. The pin (version + sha256) is supplied by the caller, never invented here.
ALIASES: dict[str, str] = {"reqeusts": "requests"}
_NEIGHBOUR_CAP = 5


@dataclass(frozen=True)
class Candidate:
    id: str
    source: Source
    target: TargetRef


@dataclass(frozen=True)
class Proposal:
    remediation: SafeRemediation
    diff: str | None


def _add(found: list[Candidate], source: Source, target: TargetRef | None) -> None:
    if target is None:
        return
    found.append(Candidate(id=f"C{len(found) + 1}", source=source, target=target))


def closed_set(
    original: TargetRef,
    *,
    pins: dict[str, tuple[str, str]],
    neighbours: list[str] | None = None,
    hf_revision: str | None = None,
    hf_safetensors_sha256: str | None = None,
    docker_tag: str | None = None,
    docker_sha256: str | None = None,
) -> list[Candidate]:
    """Build the only names a substitute is allowed to use. Ids are C1, C2, ..."""
    found: list[Candidate] = []
    good = ALIASES.get(original.name)
    if good is not None and good in pins:
        version, digest = pins[good]
        renamed = original.model_copy(update={"name": good})
        _add(found, "alias_map", pinned(renamed, version, digest))
    for name in (neighbours or [])[:_NEIGHBOUR_CAP]:
        if name == original.name or name not in pins:
            continue
        version, digest = pins[name]
        neighbour = original.model_copy(update={"name": name})
        _add(found, "top_n_neighbor", pinned(neighbour, version, digest))
    if hf_revision and hf_safetensors_sha256:
        _add(found, "hf_sibling", pinned(original, hf_revision, hf_safetensors_sha256))
    if docker_tag and docker_sha256:
        _add(found, "docker_patched_floor", pinned(original, docker_tag, docker_sha256))
    return found


def propose(
    original: TargetRef,
    original_command: str,
    candidates: list[Candidate],
    *,
    selected_id: str | None,
    recheck_evidence_ids: list[str],
    bad_token: str | None = None,
) -> Proposal:
    """Pick by id. A name or an unknown id is dropped and does not appear in the diff."""
    ids = [item.id for item in candidates]
    chosen = _choose(candidates, selected_id)
    if chosen is None or not recheck_evidence_ids:
        return Proposal(
            SafeRemediation(
                status="NO_SAFE_SUBSTITUTE" if chosen is None else "VERIFICATION_UNAVAILABLE",
                original=original,
                candidate_set_ids=ids,
            ),
            None,
        )
    requirement = approved_requirement(chosen.target)
    token = bad_token if bad_token is not None else original.name
    safe = safe_command(original_command, token, requirement)
    return Proposal(
        SafeRemediation(
            status="VERIFIED_SUBSTITUTE",
            original=original,
            candidate=chosen.target,
            candidate_source=chosen.source,
            candidate_set_ids=ids,
            selected_by="llm_rank" if selected_id else "rule",
            verification_level="static_registry",
            recheck_evidence_ids=list(recheck_evidence_ids),
            approved_requirement=requirement,
        ),
        command_diff(original_command, safe),
    )


def _choose(candidates: list[Candidate], selected_id: str | None) -> Candidate | None:
    if selected_id is None:
        return candidates[0] if len(candidates) == 1 else None
    if _ID.fullmatch(selected_id) is None:
        return None
    for item in candidates:
        if item.id == selected_id:
            return item
    return None
