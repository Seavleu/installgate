"""Pin a substitute: version + sha256. No network."""

from __future__ import annotations

import re

from contracts.contracts import Ecosystem, TargetRef

_SHA = re.compile(r"^[0-9a-f]{64}$")


def pinned(target: TargetRef, version: str, sha256: str) -> TargetRef | None:
    """Return a copy with version and sha256, or None when the pin is not 64 hex digits."""
    if not version or _SHA.fullmatch(sha256) is None:
        return None
    return target.model_copy(update={"version": version, "artifact_sha256": sha256})


def approved_requirement(target: TargetRef) -> str:
    digest = f"sha256:{target.artifact_sha256}"
    if target.ecosystem == Ecosystem.DOCKER:
        return f"{target.name}:{target.version}@{digest}"
    if target.ecosystem == Ecosystem.NPM:
        return f"{target.name}@{target.version} --hash={digest}"
    if target.ecosystem == Ecosystem.HUGGINGFACE:
        return f"{target.name}@{target.version} --hash={digest}"
    return f"{target.name}=={target.version} --hash={digest}"
