# Python cold-start storage recovery

## Incident, 2026-11-03

The production backend failed before FastAPI initialization. Requests to
`/api/_health` returned HTTP 500 / `FUNCTION_INVOCATION_FAILED`. Runtime logs
reported `No space left on device` while installing LiteLLM and PyArrow under
`/tmp`. The build reported a 463.77 MB dependency bundle and enabled runtime
dependency installation. This is not evidence of a Neon quota or schema failure.

## Packaging change

Set build-time `VERCEL_PYTHON_COMPILEALL=0` in `vercel.json`. The current Vercel
Python builder's bytecode-first packing can defer almost all public dependencies
to cold start. Disabling that optimization selects size-based package packing,
which keeps the largest packages in the deployment and reduces temporary disk
installation pressure. It does not disable Python execution or remove dependencies.

Keep `uv.lock`, PyArrow, LiteLLM, the packaged market panels, membership history,
catalogs, prompts, and migrations. They are used by live API paths. Optional ML
and AKShare dependencies are already outside the core install. The legacy
`requirements.txt` is not an equivalent deployment manifest.

This change does not upgrade the plan, enable large-function beta, change database
configuration, or execute research, trades, LLM requests, or scheduled jobs.

## Verification gate

Before production:

1. Inspect a new preview's build log. Bytecode precompilation must be absent.
2. Invoke its health endpoint for the first time, then inspect initialization logs.
   Confirm large dependencies are bundled rather than all reinstalled into `/tmp`.
3. Verify registered routes and bounded read-only data/catalog requests. An HTTP
   200 alone is insufficient if required routers failed to import.
4. Run the same read-only checks after the production rebuild. Record observations
   below; a short smoke test does not establish long-term availability.

If the platform changes its packing algorithm, recheck the build and runtime
commands instead of assuming this flag still has the same effect. If temporary
storage failures persist, investigate supported full-bundle delivery separately;
do not remove live dependencies as a workaround.

## Evidence

- Production build: `dpl_9iScPd4CXFG34hJh66LzmNQHu6Wo`, 2026-11-03 05:36 UTC.
- Runtime failure: 2026-11-03 13:26 UTC, PyArrow/LiteLLM extraction ENOSPC.
- Preview and production validation: pending.

## Rollback

Revert only this configuration change and rebuild. The prior configuration has a
known intermittent cold-start failure, so rollback is not a durable repair.

## Primary references

- [Vercel Python bundling](https://vercel.com/docs/functions/runtimes/python#controlling-what-gets-bundled)
- [Builder packing implementation](https://github.com/vercel/vercel/blob/main/packages/python/src/dependency-externalizer.ts)
- [Bytecode optimization flag](https://github.com/vercel/vercel/blob/main/packages/python/src/compileall.ts)
