-- Short-lived durable execution leases for Vercel scheduler ticks (V02).
-- Replaces holding a dedicated pool connection across unit I/O with short
-- atomic claim/fence/release transactions anchored on the database clock.
CREATE TABLE IF NOT EXISTS scheduler_job_lease (
    job text PRIMARY KEY,
    owner_token uuid,
    leased_at timestamptz,
    lease_until timestamptz,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (
        (owner_token IS NULL AND leased_at IS NULL AND lease_until IS NULL)
        OR (owner_token IS NOT NULL AND leased_at IS NOT NULL AND lease_until IS NOT NULL AND lease_until > leased_at)
    )
);

CREATE INDEX IF NOT EXISTS idx_scheduler_job_lease_active
    ON scheduler_job_lease (lease_until)
    WHERE owner_token IS NOT NULL;
