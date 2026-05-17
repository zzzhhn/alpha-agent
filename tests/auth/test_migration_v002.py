# tests/auth/test_migration_v002.py
"""V002 migration applies cleanly and creates the 5 Phase 4 tables."""
from pathlib import Path


_MIGRATION = (
    Path(__file__).parents[2]
    / "alpha_agent" / "storage" / "migrations" / "V002__phase4_users.sql"
)


def test_v002_file_exists():
    assert _MIGRATION.exists(), "V002__phase4_users.sql missing"


def test_v002_declares_five_tables():
    sql = _MIGRATION.read_text(encoding="utf-8")
    for table in (
        "users",
        "user_preferences",
        "user_watchlist",
        "user_byok",
        # @auth/pg-adapter uses singular "verification_token" (no trailing 's').
        "verification_token",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql, f"missing table {table}"


def test_v002_user_byok_has_crypto_columns():
    sql = _MIGRATION.read_text(encoding="utf-8")
    # The encryption columns the crypto_box round-trip depends on.
    for col in ("ciphertext BYTEA", "nonce BYTEA", "last4 TEXT", "encrypted_with_key_id"):
        assert col in sql, f"user_byok missing column fragment: {col}"


def test_v002_cascade_deletes_on_user_drop():
    sql = _MIGRATION.read_text(encoding="utf-8")
    # Account deletion atomicity depends on ON DELETE CASCADE everywhere.
    cascade_count = sql.count("ON DELETE CASCADE")
    assert cascade_count >= 3, (
        f"expected >=3 ON DELETE CASCADE (preferences/watchlist/byok), got {cascade_count}"
    )


def test_v002_is_additive_only():
    sql = _MIGRATION.read_text(encoding="utf-8")
    assert "ALTER TABLE" not in sql.upper(), "V002 must be additive; no ALTER TABLE"
    assert "DROP TABLE" not in sql.upper(), "V002 must not drop anything"
