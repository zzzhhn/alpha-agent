-- Private, externally evidenced borrow status. No user order or provider credentials.
CREATE TABLE event_shadow_borrow (
    source text NOT NULL, evidence_id text NOT NULL, ticker text NOT NULL, loan_id text,
    source_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    valid_until timestamptz NOT NULL, status text NOT NULL
        CHECK(status IN ('easy_to_borrow','hard_to_borrow_located','not_shortable','recalled')),
    available_shares integer CHECK(available_shares >= 0),
    annual_rate numeric CHECK(annual_rate BETWEEN 0 AND 5),
    PRIMARY KEY(source,evidence_id,ticker),
    CHECK(valid_until >= source_at)
);
CREATE INDEX event_shadow_borrow_ticker_seen ON event_shadow_borrow(ticker,received_at DESC);
