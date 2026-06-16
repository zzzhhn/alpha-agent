"""Persona-as-prompt module (A1, 2026-05-19).

Persona-bound LLM commentary generators. See registry.py for the
schema + the 8 personas alpha-agent ships."""

from alpha_agent.personas.registry import PERSONAS, get_persona

__all__ = ["PERSONAS", "get_persona"]
