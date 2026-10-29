"""Live Token Factory smoke: `uv run python -m router.smoke` (needs NEBIUS_API_KEY)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from router.token_factory import TokenFactoryError, smoke


def load_env_file() -> None:
    """Read `.env` into the process. Existing variables win. Never prints values."""
    path = Path.cwd() / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    load_env_file()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        results = asyncio.run(smoke())
    except TokenFactoryError as exc:
        print(
            json.dumps({"stage": "smoke", "failed_closed": True, "error": str(exc)}),
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    for result in results:
        print(json.dumps(result.as_log()))


if __name__ == "__main__":
    main()
