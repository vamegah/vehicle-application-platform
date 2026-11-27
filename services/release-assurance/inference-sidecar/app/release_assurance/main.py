"""FastAPI entrypoint of the release-assurance inference sidecar (task 1.1 skeleton).

Run with: uvicorn app.release_assurance.main:app
"""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

CONTEXT = "release-assurance"
HEALTH_PATH = "/api/v1/release-assurance/internal/sidecar-health"


class Health(BaseModel):
    """Body of the contracted Health schema (contracts/openapi/common/components.yaml)."""

    status: Literal["up"]
    context: str


app = FastAPI(title="AutoReliance AI release-assurance inference sidecar", version="0.1.0", openapi_url=None, docs_url=None, redoc_url=None)


@app.get(HEALTH_PATH, response_model=Health, operation_id="sidecarHealth")
def health() -> Health:
    """Internal liveness probe (x-internal-only, not routed by the gateway). Depends on no other context."""
    return Health(status="up", context=CONTEXT)
