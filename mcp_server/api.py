"""HTTP entry point (T11). POST /check returns one GateVerdict."""

from __future__ import annotations

from contracts.contracts import GateVerdict
from fastapi import FastAPI
from pydantic import BaseModel, Field

from mcp_server.check import check

app = FastAPI(title="InstallGate")


class CheckIn(BaseModel):
    command: str = Field(min_length=1, max_length=4000)


@app.post("/check", response_model=GateVerdict)
async def post_check(body: CheckIn) -> GateVerdict:
    return await check(body.command)
