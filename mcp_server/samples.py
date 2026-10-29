"""Startup snapshots for the three demo commands (T14).

`requests` was read from the PyPI JSON API on 2026-10-29: version 2.34.2,
sha256 2a0d60c1…, first upload 2011-02-14, latest upload 2026-05-14.
The other two names are absent from the registry. Missing keys are filled
once; a live cache entry is left as it is.
"""

from __future__ import annotations

from typing import Any

from engine.cache import Cache


def _osv_clear() -> dict[str, Any]:
    return {
        "malicious": False,
        "mal_ids": [],
        "mal_records": [],
        "other_ids": [],
        "queried": True,
    }


SAMPLES: dict[tuple[str, str], dict[str, Any]] = {
    ("pypi", "requests"): {
        "exists": True,
        "latest_version": "2.34.2",
        "first_upload": "2011-02-14T08:49:42.641660+00:00",
        "latest_upload": "2026-05-14T19:25:27.735762+00:00",
        "maintainers": [],
        "latest_sha256": "2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0",
        "release_count": 163,
    },
    ("osv", "PyPI:requests"): _osv_clear(),
    ("pypi", "reqeusts"): {"exists": False},
    ("osv", "PyPI:reqeusts"): _osv_clear(),
    ("pypi", "no-such-pkg-xyz"): {"exists": False},
    ("osv", "PyPI:no-such-pkg-xyz"): _osv_clear(),
}


def warm(cache: Cache) -> int:
    written = 0
    for (source, key), facts in SAMPLES.items():
        if cache.get(source, key) is None:
            cache.set(source, key, facts)
            written += 1
    return written
