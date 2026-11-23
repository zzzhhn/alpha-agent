-- Observation only. No order, holding, trading signal, or paper book is written.
CREATE TABLE official_event_reaction (
    event_id BIGINT PRIMARY KEY REFERENCES official_event_watch(id),
    known_at TIMESTAMPTZ NOT NULL,
    session_date DATE NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL CHECK (observed_at >= known_at),
    next_check_at TIMESTAMPTZ,
    timing TEXT NOT NULL CHECK (timing IN ('overnight', 'intraday', 'late_discovery')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'observed', 'partial', 'unavailable')),
    gap JSONB,
    anchor JSONB,
    follow_through JSONB,
    gap_reason TEXT,
    follow_reason TEXT,
    CHECK ((status='pending') = (next_check_at IS NOT NULL))
);

CREATE INDEX official_event_reaction_due_idx ON official_event_reaction(next_check_at)
    WHERE status='pending';
CREATE INDEX official_event_watch_reaction_candidates_idx ON official_event_watch(first_seen_at,id)
    WHERE status='observed' AND published_at IS NOT NULL AND published_at_quality IN ('sec_accepted','source_timestamp')
        AND kind IN ('management_change','earnings','guidance','merger_acquisition','regulatory');
