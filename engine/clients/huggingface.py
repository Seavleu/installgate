"""Hugging Face Hub model metadata. We read the file list; we never load weights."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from contracts.contracts import TargetRef

from engine.cache import Cache
from engine.clients import get_json

BASE = "https://huggingface.co/api/models"

PICKLE_SUFFIXES = (".bin", ".pt", ".pth", ".pkl", ".ckpt")
SAFE_SUFFIXES = (".safetensors",)


def model_url(repo_id: str) -> str:
    return f"{BASE}/{repo_id}"


def summarise(body: dict[str, Any] | None) -> dict[str, Any]:
    if body is None:
        return {"exists": False}

    filenames = [
        str(s.get("rfilename"))
        for s in (body.get("siblings") or [])
        if isinstance(s, dict) and s.get("rfilename")
    ]
    pickle_files = [f for f in filenames if f.lower().endswith(PICKLE_SUFFIXES)]
    safetensors_files = [f for f in filenames if f.lower().endswith(SAFE_SUFFIXES)]

    created_raw = str(body.get("createdAt") or "")
    modified_raw = str(body.get("lastModified") or "")

    def _parse(raw: str) -> str | None:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC).isoformat()
        except ValueError:
            return None

    return {
        "exists": True,
        "files": filenames,
        "pickle_files": pickle_files,
        "safetensors_files": safetensors_files,
        "has_pickle": bool(pickle_files),
        "has_safetensors": bool(safetensors_files),
        "first_upload": _parse(created_raw),
        "latest_upload": _parse(modified_raw),
        "sha": body.get("sha"),
    }


async def fetch(
    client: httpx.AsyncClient, target: TargetRef, cache: Cache | None = None
) -> dict[str, Any]:
    if cache is not None:
        cached = cache.get("huggingface", target.name)
        if cached is not None:
            return dict(cached)
    body = await get_json(client, model_url(target.name), allow_404=True)
    facts = summarise(body)
    if cache is not None:
        cache.set("huggingface", target.name, facts)
    return facts
