"""Minimal Vercel serverless test."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "alphacore", "mode": "minimal-test"}
