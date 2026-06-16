-- Serenity supply-chain bottleneck scorecard per ticker (integration seam #2).
-- Written by a research session (a serenity supply-chain study scored via
-- alpha_agent.signals.supply_chain_scorecard), read by the supply_chain signal
-- to map final_score -> z. The inputs are qualitative research outputs, NOT
-- auto-derived market data, so this table is populated ad-hoc by research, not
-- by a daily ingest cron. Empty is the normal early state (most names unscored).
CREATE TABLE IF NOT EXISTS supply_chain_scorecard (
    ticker       TEXT PRIMARY KEY,
    final_score  DOUBLE PRECISION NOT NULL,            -- 0-100 bottleneck score
    verdict      TEXT NOT NULL DEFAULT '',
    factors      JSONB NOT NULL DEFAULT '{}'::jsonb,   -- 8 factor ratings 0-5
    penalties    JSONB NOT NULL DEFAULT '{}'::jsonb,   -- 8 penalty ratings 0-5
    evidence     JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{claim, source, strength}]
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
