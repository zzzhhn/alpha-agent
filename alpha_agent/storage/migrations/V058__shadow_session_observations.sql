-- At most three rows per exchange session. A missing live mark is never zero.
CREATE TABLE event_shadow_session_sample (
    policy text NOT NULL, session_date date NOT NULL, sleeve text NOT NULL,
    sampled_at timestamptz NOT NULL, nav numeric, open_positions integer NOT NULL,
    PRIMARY KEY(policy,session_date,sleeve)
);
