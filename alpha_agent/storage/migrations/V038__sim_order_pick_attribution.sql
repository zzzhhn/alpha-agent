-- alpha_agent/storage/migrations/V038__sim_order_pick_attribution.sql
-- Paper trading V2 P0 (backend):
-- 1. Attribution: when an order is placed from a pick's inline drawer, tag it
--    with the pick's date+ticker so /api/paper/attribution can split PnL into
--    "followed a pick" vs "self-directed". NULL for manual /paper orders and
--    all pre-existing rows (additive, backward compatible).
-- 2. Fill-time cash re-check: order-time validation only estimates against
--    cash at submission; by the time the daily cron fills the order, an
--    earlier fill in the same batch may have already spent that cash. Such
--    orders need a terminal state distinct from 'expired' (which is reserved
--    for oversell/no-cross) so the UI can show why the order never filled.
--    Extends the existing status CHECK rather than adding a parallel column.
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS pick_date DATE;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS pick_ticker TEXT;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS fail_reason TEXT;

ALTER TABLE sim_order DROP CONSTRAINT IF EXISTS sim_order_status_check;
ALTER TABLE sim_order
  ADD CONSTRAINT sim_order_status_check
  CHECK (status IN ('pending', 'filled', 'expired', 'cancelled', 'failed'));
