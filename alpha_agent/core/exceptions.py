"""Shared exception types."""


class ProviderUnavailableError(RuntimeError):
    """LLM provider health check failed at startup."""


class LLMEmptyResponseError(RuntimeError):
    """The provider completed a request without user-visible text."""


class FactorValidationError(ValueError):
    """FactorSpec failed Pydantic/AST/smoke-test validation."""


class DataIntegrityError(RuntimeError):
    """Panel data violates expected invariants (e.g., non-trading-day dates)."""
