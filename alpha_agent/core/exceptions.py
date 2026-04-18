"""Shared exception types."""


class ProviderUnavailableError(RuntimeError):
    """LLM provider health check failed at startup."""


class FactorValidationError(ValueError):
    """FactorSpec failed Pydantic/AST/smoke-test validation."""
