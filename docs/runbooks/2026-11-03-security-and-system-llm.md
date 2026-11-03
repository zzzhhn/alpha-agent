# Security patch and system-default LLM boundary

## Scope and findings

2026-11-03: patch the frontend's known production dependency advisories, then
trace the `KIMI_API_KEY` startup warning without altering personal BYOK credentials.

### Security patch

| Package | Before | After |
| --- | --- | --- |
| Next.js / eslint-config-next | 15.5.25 | 15.5.28 |
| sharp | 0.35.4 | 0.35.5 |
| Nodemailer | 10.0.0 | 10.1.4 |
| Zod | 4.3.6 | 4.6.7 |
| source-map-js | 1.2.1 | 1.2.2 |

The lockfile also updates matching Next/SWC, sharp/libvips platform packages and
the sharp WebAssembly runtime dependency. No framework major-version migration,
authentication redesign, new feature dependency, or database change is included.

Next's upstream advisory identifies 15.5.28 and sharp >=0.35.5 as patched versions.
The installed old versions matched the advisory; this is not a claim that the
production application had been exploited. `npm audit --omit=dev` went from eight
findings (one Critical) to zero after the bounded production dependency updates.
This result does not assert that development dependencies have no advisories.

## Why the Kimi warning appeared

Both preview and production already have `ALPHACORE_REQUIRE_BYOK=true`, confirmed
through the Vercel configuration API. The normal FastAPI entrypoint honored that
flag, but `api/index.py`, the actual production entrypoint, always attempted to
create an optional platform client. The default provider is Kimi; with no platform
key it logged an initialization failure even though BYOK-only mode was intentional.

The fix makes the production entrypoint skip only the optional platform client in
BYOK-only mode, matching `alpha_agent/api/app.py`. When the flag is false, genuine
platform configuration failures remain recorded and logged. This is not a blanket
suppression of LLM errors and does not add a shared-key fallback.

## Actual impact by feature

| Feature / runner | Actual credential source | Effect of missing Vercel KIMI_API_KEY |
| --- | --- | --- |
| Alpha translation, authenticated LLM APIs | Authenticated user's encrypted BYOK via `api/byok.py` | No direct effect; missing user key still fails with 400, invalid auth with 401 |
| Streaming Rich Brief | Authenticated user's BYOK | No direct effect; individual provider/auth failures remain reported |
| Lean brief and numeric recommendations | Deterministic data/logic | Do not depend on the optional platform client |
| Paper investment bot | Bot account owner's BYOK, resolved by `trading/bot_runner.py` | No direct effect; worker records owner-credential/model failures |
| Factor proposals | Job owner's BYOK, through `factor_lab.py` and cron job route | No direct effect; job failures remain visible |
| Daily factor research | Authorized SYSTEM_USER_ID plus that user's BYOK for the LLM arm | Separate identity/credential requirements; GA arm is independent |
| BRAIN mining | Independent BRAIN credentials; MINING_LLM_KEY in GitHub Actions for optional LLM screening | No direct effect; missing mining LLM key uses deterministic evidence screening, not a successful LLM screen |
| Standalone CLI / old Streamlit research pipeline configured for Kimi | System provider settings and KIMI_API_KEY | These independent entrypoints require the system key and fail without it |

The former global news enrichment cron is removed. Its legacy worker helper is
not evidence of an active production job outage. GitHub's mining key and Vercel's
system key are different settings; do not copy a user's BYOK into either one as
an implicit repair.

## Preservation and verification

- No environment variables, ciphertext, nonce, BYOK master key, user model, base
  URL, or provider metadata were changed. No migration or credential-write route
  is involved in this patch.
- A regression test runs the real Vercel entrypoint with BYOK-only mode on/off and
  an empty system key. It failed before the guard was added and passed after.
- Existing BYOK resolution and Alpha authentication tests cover stored-key
  decryption, absent master key, absent personal credential, custom model/endpoint,
  and Kimi-compatible endpoint routing without paid model calls.
- Auth/password/reset-flow and saved-connection tests validate the affected
  frontend dependencies (30 tests passed); backend startup/BYOK/translation
  authentication checks passed (14 tests). The Next.js 15.5.28 production build
  passed. It retains the existing RecentRunsTable hook warning and reports jose
  compression-API Edge warnings; authenticated production navigation is part of
  release validation. Preview and release receipts are
  recorded in the pull request; do not infer deployment from this document alone.
- No research, bot, mining, trade, or paid LLM run is triggered for this audit.
  Successful metadata or route checks do not prove an upstream model is reachable.

## Primary references

- [Next.js security advisory](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw)
- [Nodemailer 10.1.4 fixes](https://github.com/nodemailer/nodemailer/releases/tag/v10.1.4)
- [Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)
- [source-map-js advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q)

Code references: `api/index.py`, `alpha_agent/api/app.py`, `api/byok.py`,
`api/routes/brief.py`, `api/routes/interactive.py`, `api/routes/factor_lab.py`,
`api/routes/cron_routes.py`, `trading/bot_runner.py` (the last paths are under
`alpha_agent/`); `.github/workflows/brain-mining-loop.yml` and
`scripts/brain_mining_loop.py` describe the separate GitHub runner.
