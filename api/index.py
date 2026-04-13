"""Vercel serverless entry point — incremental test."""

import sys
import os

# Force serverless detection
os.environ.setdefault("SERVERLESS", "true")

from fastapi import FastAPI

app = FastAPI()


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "mode": "step2-test"}


# Step 2: try importing the config and LLM factory
@app.get("/api/debug/imports")
async def debug_imports() -> dict:
    results = {}
    for mod_name in [
        "alpha_agent.config",
        "alpha_agent.api.cache",
        "alpha_agent.llm.base",
        "alpha_agent.llm.openai",
        "alpha_agent.llm.ollama",
        "alpha_agent.llm.factory",
        "alpha_agent.api.security",
        "alpha_agent.api.routes.system",
        "alpha_agent.api.routes.serverless",
    ]:
        try:
            __import__(mod_name)
            results[mod_name] = "ok"
        except Exception as e:
            results[mod_name] = f"FAIL: {type(e).__name__}: {e}"
    return {"imports": results, "python": sys.version}
