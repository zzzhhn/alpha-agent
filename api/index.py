"""Vercel serverless entry point — exports the FastAPI app.

Vercel's Python runtime auto-detects the FastAPI instance and wraps it
as a serverless handler. All routing is handled internally by FastAPI.
"""

from alpha_agent.api.app import app  # noqa: F401
