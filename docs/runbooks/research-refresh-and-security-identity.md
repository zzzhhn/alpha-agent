# Research refresh and security identity, 2026-11-01

## Updated research inputs

The previous April 30 panel is superseded by adjusted Alpaca SIP OHLCV through
October 30, the latest completed US session: 413,670 rows, 570 symbols including
SPY/RSP. The evaluator uses the last 504 sessions and 568 equity symbols.
Current-universe quote coverage is 502/503 (99.80%); PSKY has no latest quote
and remains missing, not forward-filled or replaced with PARA.

Historical membership is supplemented with S&P's officially effective September
21, October 1 and October 6 changes; source URLs and actions live in
`membership_updates.json`. The announced November 4 change is not used early.
The live cron universe now comes from latest membership, not the union of every
historical ticker. Historical members are retained for historical research.

The existing Compustat fundamentals are preserved. SEC companyfacts adds 1,051
filing-dated snapshots for 521 issuers. A new fact is usable the day after its
actual filing date; annual/YTD flows are never substituted for quarterly flows.
Missing fields remain missing; facts expire after 200 calendar days. SEC GAAP
net income is not equivalent to vendor-adjusted earnings. Sector classifications
remain snapshots; adjusted prices are not point-in-time price vintages. Neither
the dataset nor repeated historical holdouts establish live profitability.

`research_dataset.json` records sources, coverage, dates and limitations. This
update is packaged as bounded Parquet artifacts, not duplicated into Neon.
Refresh explicitly on the maintenance machine:

```sh
python -m scripts.refresh_research_dataset --through YYYY-MM-DD --env-file /secure/path/.env
```

The date must be a completed session. `--prices-only` preserves existing PIT
fundamentals; `--fundamentals-only` preserves OHLCV. No scheduler or new paid
provider is added. Review membership notices and the manifest before committing.

## PARA is an issuer collision, not an ordinary quote gap

- Paramount Global's merger completed August 7, 2025; the new company used PSKY.
  Cash/stock elections prevent treating every old holding as an automatic rename.
- An unrelated issuer, Banzai/Parabolic, reused PARA from August 7, 2026. It had
  a 1-for-10 reverse split on October 27, 2026.
- Our old legacy and tactical research books contain filled PARA orders after
  the original issuer's retirement. Production quotes from July–October 2026
  belong to the unrelated issuer. The previously reported tactical -6.66% is
  **invalid performance evidence**, not a reliable loss estimate.

Official evidence:
[Paramount merger](https://www.sec.gov/Archives/edgar/data/2041610/000119312525175046/d841914dex991.htm),
[PARA ticker reuse](https://www.sec.gov/Archives/edgar/data/1826011/000119312526352584/2q_2026_10-q_sticker_296.htm),
[reverse split](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-765).

The known identity boundary caps historical PARA at August 6, 2025 and excludes
it from current ingestion, recommendations and target selection. Both affected
drivers stop before generating/filling/marking more activity. APIs and existing
Design System states explain quarantine and hide invalid performance, including
turnover replay. All records remain intact; no deletion, PSKY substitution,
invented prices, liquidation, or personal `sim_` account changes occur.

A clean tactical account is a separate prospective version, not a corrected
history. Its creation awaits the owner's explicit choice. Strategic is separate
and continues unchanged. This narrow registry is not a complete security master;
other corporate actions still require issuer-level reconciliation.

## LLM execution and request budget

Production `SYSTEM_USER_ID` identifies the existing administrator and resolves
that owner's encrypted BYOK configuration. It must pass the administrator check.
No credentials are copied into code, workflow files or logs. A missing identity
is a business error, not a successful skipped LLM run.

GA, generation, parsing retry, candidate validation and optional skeptic review
share a 270-second cron deadline under Vercel's 300-second limit. Generation
reserves 45 seconds for validation; optional skeptic calls use only remaining
time and explicitly record whether completed. An empty proposal response is
not success. Receipts include generated count, model and generation duration.
Generated candidates remain subject to existing validation gates and manual
approval; no gate is weakened to manufacture a passing result.

## Release gates

Focused unit/research checks: 18 passed. Refreshed control and default expression
both execute on real chronological data. Frontend TypeScript and Design System
checks pass. Production confirmation must follow the actual deployment switch:
read-only research canary, then one full daily loop including LLM, then inspect
the audit/proposal rows and quarantine API/UI. HTTP 200 or an empty queue alone
is not sufficient proof. Exact production receipts belong in the closure report.
