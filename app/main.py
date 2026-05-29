"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.engagements import router as engagements_router
from app.api.documents import router as documents_router
from app.api.pipeline import router as pipeline_router
from app.api.gates import router as gates_router
from app.api.audit import router as audit_router
from app.api.seal import router as seal_router

app = FastAPI(
    title="Covenant Compliance Platform",
    version="1.0.0",
    description="Private-credit covenant compliance — audit-grade",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(engagements_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(pipeline_router, prefix="/api/v1")
app.include_router(gates_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(seal_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"ok": True}
