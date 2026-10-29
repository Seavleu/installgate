"""HTTP entry point (T11, T14). POST /check returns one GateVerdict.

POST /check/stream sends the same check as NDJSON stage lines, then the verdict.
/mcp serves the check_install tool over MCP Streamable HTTP.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from contracts.contracts import GateVerdict
from engine.cache import Cache
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response as StarletteResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_server.check import check
from mcp_server.limit import client_key, limit_per_minute, limiter
from mcp_server.samples import warm
from mcp_server.server import server
from mcp_server.spend import was_capped

_log = logging.getLogger("installgate.api")
_LIMITED = {"/check", "/check/stream", "/mcp"}

_mcp: dict[str, ASGIApp] = {}


async def _mcp_asgi(scope: Scope, receive: Receive, send: Send) -> None:
    await _mcp["app"](scope, receive, send)


def configure_logging() -> None:
    """JSON lines from installgate.* loggers to stderr at LOG_LEVEL. Uvicorn does not do this."""
    level = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    root = logging.getLogger("installgate")
    root.setLevel(level if level in logging.getLevelNamesMapping() else "INFO")
    # The MCP SDK puts a rich handler on the root logger; one JSON line per event is enough.
    root.propagate = False
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    cache = Cache(os.environ.get("CACHE_PATH", "./.cache/installgate.sqlite"))
    try:
        warm(cache)
    finally:
        cache.close()
    # A session manager runs once, so each lifespan gets a new one. Stateless JSON: one
    # POST in, one JSON-RPC response out. host="0.0.0.0" skips the localhost-only Host
    # check, which would reject the UI proxy and hosted judges.
    _mcp["app"] = server.streamable_http_app(
        stateless_http=True, json_response=True, host="0.0.0.0"
    )
    async with server.session_manager.run():
        yield


app = FastAPI(title="InstallGate", lifespan=lifespan)


class CheckIn(BaseModel):
    command: str = Field(min_length=1, max_length=4000)


@app.middleware("http")
async def limit_checks(request: Request, call_next: RequestResponseEndpoint) -> StarletteResponse:
    if request.method == "POST" and request.url.path in _LIMITED:
        if not limiter.allow(client_key(request), limit=limit_per_minute()):
            return JSONResponse(
                {"detail": "Too many checks. Wait a minute."},
                status_code=429,
            )
    return await call_next(request)


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/check", response_model=GateVerdict)
async def post_check(body: CheckIn, response: Response) -> GateVerdict:
    verdict = await check(body.command)
    if was_capped():
        response.headers["X-InstallGate-Spend"] = "capped"
    return verdict


@app.post("/check/stream")
async def post_check_stream(body: CheckIn) -> StreamingResponse:
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()

    async def run() -> GateVerdict:
        try:
            return await check(body.command, on_stage=queue.put_nowait)
        finally:
            queue.put_nowait(None)

    async def lines() -> AsyncIterator[str]:
        task = asyncio.create_task(run())
        while (event := await queue.get()) is not None:
            yield json.dumps({"type": "stage", **event}) + "\n"
        try:
            verdict = await task
        except Exception:
            _log.exception("stream check failed")
            yield json.dumps({"type": "error", "detail": "check failed; treat as REVIEW"}) + "\n"
            return
        yield (
            json.dumps(
                {
                    "type": "verdict",
                    "spend_capped": was_capped(),
                    "verdict": verdict.model_dump(mode="json"),
                }
            )
            + "\n"
        )

    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


app.mount("/", _mcp_asgi)
