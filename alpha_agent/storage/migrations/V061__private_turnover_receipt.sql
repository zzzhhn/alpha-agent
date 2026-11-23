-- Immutable account-owned audit summary, not supplier quotes or historical fills.
CREATE TABLE paper_turnover_receipt (
    account_id bigint NOT NULL REFERENCES sim_account(id),
    cohort_id integer NOT NULL, start_date date NOT NULL, end_date date NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    metrics jsonb NOT NULL, provenance text NOT NULL,
    PRIMARY KEY(account_id,cohort_id,start_date,end_date),
    CHECK(end_date >= start_date)
);
