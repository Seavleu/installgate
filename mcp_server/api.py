"""HTTP entry point (T11, T14). POST /check returns one GateVerdict."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from contracts.contracts import GateVerdict
from engine.cache import Cache
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response as StarletteResponse

from mcp_server.check import check
from mcp_server.limit import client_key, limit_per_minute, limiter
from mcp_server.samples import warm
from mcp_server.spend import was_capped


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    cache = Cache(os.environ.get("CACHE_PATH", "./.cache/installgate.sqlite"))
    try:
        warm(cache)
    finally:
        cache.close()
    yield


app = FastAPI(title="InstallGate", lifespan=lifespan)


class CheckIn(BaseModel):
    command: str = Field(min_length=1, max_length=4000)


@app.middleware("http")
async def limit_checks(request: Request, call_next: RequestResponseEndpoint) -> StarletteResponse:
    if request.method == "POST" and request.url.path == "/check":
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
