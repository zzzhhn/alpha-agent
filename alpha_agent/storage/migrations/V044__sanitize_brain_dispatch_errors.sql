-- A malformed GH_PAT header can make h11 include the rejected Authorization
-- value in LocalProtocolError text.  Older BRAIN dispatch code persisted that
-- raw exception string.  Keep the diagnostic class while removing any header
-- contents from the durable run ledger.
UPDATE brain_runs
SET error_detail = 'dispatch failed: LocalProtocolError'
WHERE error_detail LIKE 'dispatch failed: LocalProtocolError:%'
   OR error_detail LIKE '%Bearer %';
