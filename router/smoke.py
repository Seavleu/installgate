"""Live Token Factory smoke: `uv run python -m router.smoke` (needs NEBIUS_API_KEY)."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

from router.token_factory import TokenFactoryError, smoke


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        result = asyncio.run(smoke())
    except TokenFactoryError as exc:
        print(
            json.dumps({"stage": "smoke", "failed_closed": True, "error": str(exc)}),
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    print(json.dumps(result.as_log()))


if __name__ == "__main__":
    main()
