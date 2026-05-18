-- V007__news_reasoning_text.sql (2026-05-19)
--
-- Add a freeform LLM-reasoning text column to news_items so the per-headline
-- enrichment can surface a 2-3 sentence analysis next to the red/green/gray
-- sentiment dot. Prior to this column, the only LLM output stored per row
-- was sentiment_score (float) + sentiment_label (enum) — useful for color
-- coding but the user has no way to see *why* the LLM scored it that way.
--
-- reasoning_lang tracks the language the LLM was asked to output in
-- (currently "zh" or "en"; matches the requesting user's locale at enrich
-- time). The frontend NewsBlock displays the text as-is and uses the lang
-- field for the lang= attribute / accessibility hint, but does not
-- auto-translate. A future polish could store both languages.
ALTER TABLE news_items
    ADD COLUMN IF NOT EXISTS reasoning_text text,
    ADD COLUMN IF NOT EXISTS reasoning_lang text;
