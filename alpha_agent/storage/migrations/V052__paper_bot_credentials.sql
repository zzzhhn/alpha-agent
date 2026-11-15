-- Optional account-scoped key. Existing bots keep using the owner's BYOK.
CREATE TABLE IF NOT EXISTS sim_bot_credential (
    account_id bigint PRIMARY KEY REFERENCES sim_account(id) ON DELETE CASCADE,
    provider text NOT NULL CHECK (provider IN ('openai', 'anthropic', 'kimi', 'ollama')),
    base_url text,
    ciphertext bytea NOT NULL,
    nonce bytea NOT NULL,
    last4 text NOT NULL,
    encrypted_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz
);
