-- Private forward observations, deliberately not recommendation or order rows.
CREATE TABLE premarket_review (
    user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_date date NOT NULL,
    stage text NOT NULL CHECK (stage IN ('premarket','open_review','evaluation')),
    captured_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (user_id, session_date, stage)
);
