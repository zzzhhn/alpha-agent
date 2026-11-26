"""Version evidence and eligibility for restoring BYOK settings."""
import json
from urllib.parse import urlsplit

from alpha_agent.settings.change_log import ROLLBACK_SAFE_FIELDS


def safe_endpoint(value: str | None) -> bool:
    """Allow endpoint URLs with custom paths and no URL-embedded auth."""
    if value is None:
        return True
    try:
        url = urlsplit(value)
        return (
            url.scheme in {"http", "https"}
            and bool(url.hostname)
            and url.username is None
            and url.password is None
            and not any(char in value for char in ("?", "#", "\\"))
            and not any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
        )
    except ValueError:
        return False


def credential_evidence(provider: str, revision: str, old_provider: str | None) -> dict:
    return {"byok": {"provider": provider, "encrypted_at": revision, "old_provider": old_provider}}


def byok_evidence(change: dict) -> dict:
    raw = change["evidence"]
    evidence = json.loads(raw) if isinstance(raw, str) else raw
    binding = evidence.get("byok") if isinstance(evidence, dict) else None
    return binding if isinstance(binding, dict) else {}


def rollback_status(change: dict, credential) -> str:
    field = change["field"]
    if field not in ROLLBACK_SAFE_FIELDS or change["rollback_of"] is not None:
        return "read_only"
    if change["already_rolled_back"]:
        return "already_rolled_back"
    evidence = byok_evidence(change)
    provider = evidence.get("provider")
    revision = evidence.get("encrypted_at")
    if not isinstance(provider, str) or not isinstance(revision, str):
        return "unverified"
    if evidence.get("old_provider") != provider:
        return "different_provider"
    if field == "byok.base_url" and not all(
        safe_endpoint(change[key]) for key in ("old_value", "new_value")
    ):
        return "unverified"
    if credential is None or credential["provider"] != provider:
        return "different_provider"
    if credential["encrypted_at"].isoformat() != revision:
        return "stale_revision"
    if credential[ROLLBACK_SAFE_FIELDS[field]] != change["new_value"]:
        return "value_changed"
    return "available"
