-- Record only changes in continuous 20-minute coverage, rather than every poll.
-- The migration starts forward observation; it cannot establish older health.
ALTER TABLE official_event_source ADD COLUMN tracked_since timestamptz NOT NULL DEFAULT clock_timestamp();

CREATE TABLE official_source_coverage (
    ticker text NOT NULL,
    source text NOT NULL,
    first_success_at timestamptz NOT NULL,
    last_success_at timestamptz NOT NULL,
    failed_at timestamptz,
    PRIMARY KEY (ticker, source, first_success_at),
    CHECK (last_success_at >= first_success_at)
);
CREATE INDEX official_source_coverage_recent ON official_source_coverage(last_success_at);

CREATE FUNCTION record_official_source_coverage() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    observation timestamptz := clock_timestamp();
    previous_start timestamptz;
BEGIN
    -- The source upsert already serializes writers for this ticker and feed.
    IF NEW.last_error IS NOT NULL THEN
        UPDATE official_source_coverage SET failed_at = observation
        WHERE ticker = NEW.ticker AND source = NEW.source AND failed_at IS NULL
          AND last_success_at >= observation - interval '20 minutes';
        RETURN NEW;
    END IF;
    IF NEW.last_success_at IS NULL THEN RETURN NEW; END IF;
    -- The completion time is sampled after acquiring the source row. A writer
    -- delayed on that row cannot introduce an observation before its turn.

    SELECT first_success_at INTO previous_start FROM official_source_coverage
    WHERE ticker = NEW.ticker AND source = NEW.source AND failed_at IS NULL
      AND last_success_at BETWEEN observation - interval '20 minutes' AND observation
    ORDER BY first_success_at DESC LIMIT 1;
    IF FOUND THEN
        UPDATE official_source_coverage SET last_success_at = observation
        WHERE ticker = NEW.ticker AND source = NEW.source AND first_success_at = previous_start;
    ELSE
        INSERT INTO official_source_coverage(ticker,source,first_success_at,last_success_at)
        VALUES (NEW.ticker,NEW.source,observation,observation);
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER official_source_coverage_write AFTER INSERT OR UPDATE OF last_success_at,last_error
ON official_event_source FOR EACH ROW EXECUTE FUNCTION record_official_source_coverage();
