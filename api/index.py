"""Vercel serverless — step-by-step debug build."""

import os
import sys

os.environ.setdefault("SERVERLESS", "true")

from fastapi import FastAPI

app = FastAPI(title="AlphaCore")

# Step 1: health (worked)
@app.get("/api/health")
async def health():
    return {"status": "ok", "step": "3-routes"}

# Step 2: import and register serverless routes
try:
    from alpha_agent.api.routes.serverless import router as sr
    app.include_router(sr)
    print("✓ serverless routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    print(f"✗ serverless routes: {e}", file=sys.stderr, flush=True)

# Step 3: import and register system routes
try:
    from alpha_agent.api.routes.system import router as sys_r
    app.include_router(sys_r)
    print("✓ system routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    print(f"✗ system routes: {e}", file=sys.stderr, flush=True)

print(f"App ready: {len(app.routes)} routes", file=sys.stderr, flush=True)
