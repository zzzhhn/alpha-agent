# Tactical v3: owner-authorized clean forward restart

On 2026-11-01 the owner approved preserving the PARA-contaminated tactical book
and starting a clean recommendation-validation account. This is a research
simulation, not a brokerage account or a personal `sim_` account reset.

- Tactical `canonical_top50_continuous` moves from version 2 to version 3.
- Strategic stays version 2. No policy, fee, rebalance or capital changes.
- Initial simulated cash remains USD 1,000,000; no inherited positions, costs,
  orders or performance. The old version, including PARA, remains quarantined.
- `ensure_book` creates one idempotent new account using existing tables. No
  migration, deletion, liquidation or manual mutation of the old account.
- The new account retains a predecessor ID and an immutable next-session signal
  start date. It also keeps the latest existing complete run as its forward ID
  boundary. A new run ID for an old session cannot bypass the date boundary.
- Repeated initialization preserves the activation date, policy parameters,
  cash and boundary. API readers select the newest version and report the
  predecessor, restart reason and earliest signal date.

For initialization on Sunday November 1, the earliest eligible recommendation
is the November 2 session. Under existing T+1-close execution, the earliest
simulated fill is November 3, subject to a complete eligible recommendation and
available prices. Until then an empty book is expected, not a missing-data bug.
There is no reconstructed historical curve and no implication of profitability.

Release verification: focused real-Postgres test covers preservation, a duplicate
old-session snapshot, the new-session gate, idempotency and API version selection.
After the production deployment switches, run one bounded `l2_cycle`, inspect the
new account and read the existing paper/evidence interface. Preserve the old
account and strategic balances/order/valuation counts in the closure receipt.
