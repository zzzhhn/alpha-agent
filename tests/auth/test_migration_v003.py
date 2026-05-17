# tests/auth/test_migration_v003.py
"""V003 migration adds password_hash + the accounts / password_reset_codes
/ auth_rate_limit tables. Phase 4b multi-method auth.

Mirrors tests/auth/test_migration_v002.py: pure file-content assertions,
no live database connection."""
from pathlib import Path


_MIGRATION = (
    Path(__file__).parents[2]
    / "alpha_agent" / "storage" / "migrations" / "V003__phase4b_multi_auth.sql"
)


def test_v003_file_exists():
    assert _MIGRATION.exists(), "V003__phase4b_multi_auth.sql missing"


def test_v003_adds_password_hash_column():
    sql = _MIGRATION.read_text(encoding="utf-8")
    assert "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT" in sql, (
        "V003 must add the nullable users.password_hash column"
    )


def test_v003_declares_three_new_tables():
    sql = _MIGRATION.read_text(encoding="utf-8")
    for table in ("accounts", "password_reset_codes", "auth_rate_limit"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql, f"missing table {table}"


def test_v003_accounts_has_camelcase_adapter_columns():
    sql = _MIGRATION.read_text(encoding="utf-8")
    # @auth/pg-adapter uses double-quoted camelCase identifiers. The G2 audit
    # found these; the implementer re-verified them against node_modules.
    for col in ('"userId"', '"providerAccountId"'):
        assert col in sql, f"accounts table missing camelCase column {col}"
    assert "REFERENCES users(id) ON DELETE CASCADE" in sql, (
        "accounts.userId must FK to users(id) ON DELETE CASCADE"
    )
    assert 'UNIQUE (provider, "providerAccountId")' in sql, (
        "accounts needs the (provider, providerAccountId) unique constraint"
    )


def test_v003_password_reset_codes_columns():
    sql = _MIGRATION.read_text(encoding="utf-8")
    for fragment in (
        "code_hash TEXT NOT NULL",
        "expires_at TIMESTAMPTZ NOT NULL",
        "used BOOLEAN NOT NULL DEFAULT false",
    ):
        assert fragment in sql, f"password_reset_codes missing: {fragment}"


def test_v003_auth_rate_limit_columns():
    sql = _MIGRATION.read_text(encoding="utf-8")
    for fragment in (
        "bucket_key TEXT NOT NULL",
        "window_start TIMESTAMPTZ NOT NULL",
        "hit_count INT NOT NULL DEFAULT 0",
        "PRIMARY KEY (bucket_key, window_start)",
    ):
        assert fragment in sql, f"auth_rate_limit missing: {fragment}"


def test_v003_is_additive_only():
    sql = _MIGRATION.read_text(encoding="utf-8")
    # Exactly one ALTER TABLE (the additive ADD COLUMN). No DROP at all.
    assert sql.upper().count("ALTER TABLE") == 1, (
        "V003 must contain exactly one ALTER TABLE (the additive password_hash add)"
    )
    assert "DROP TABLE" not in sql.upper(), "V003 must not drop anything"
    assert "DROP COLUMN" not in sql.upper(), "V003 must not drop any column"
