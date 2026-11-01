"""Manually dispatched recovery only. One bounded request, no automatic retry.

HTTP success and row counts do not prove freshness. Verify actual price dates,
coverage and storage delta before expanding a canary or enabling schedules.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cron_preflight import check


def recovery_path(operation: str, limit: int, offset: int, run_id: str) -> str:
    if operation in ("daily_prices", "fast_intraday"):
        cap = 75 if operation == "daily_prices" else 40
        if not 1 <= limit <= cap or not 0 <= offset <= 600:
            raise ValueError("Recovery slice exceeds the allowed bounds")
        params = {"limit": limit, "offset": offset}
        if operation == "daily_prices":
            params["period"] = "3mo"
        else:
            params["run_key"] = f"recovery-{run_id}-{offset}"
        return operation + "?" + urlencode(params)
    if operation == "publish_recommendation":
        return operation + "?" + urlencode({"request_id": f"recovery-{run_id}"})
    if operation in ("research_validation", "run_propose_jobs", "daily_factor_loop", "l2_cycle"):
        return operation
    raise ValueError("Operation outside recovery scope")


def result_ok(operation: str, body: dict) -> bool:
    if operation == "daily_prices":
        return body.get("updated", 0) > 0 and not body.get("error_count")
    if body.get("ok") is not True or body.get("errors"):
        return False
    if operation == "fast_intraday":
        return body.get("rows_written", 0) > 0
    if operation == "run_propose_jobs":
        return all(job.get("status") == "done" for job in body.get("jobs", []))
    if operation == "daily_factor_loop":
        for arm in ("ga", "llm"):
            result = body.get(arm) or {}
            rejects = (result.get("_diag") or {}).get("rejects", [])
            if result.get("error") or result.get("ok") is False or any(r.get("reason") == "fold_kernel_exception" for r in rejects):
                return False
        return True
    return True


def main() -> int:
    operation = os.environ["RECOVERY_OPERATION"]
    path = recovery_path(operation, int(os.environ.get("RECOVERY_LIMIT", "5")),
                         int(os.environ.get("RECOVERY_OFFSET", "0")),
                         os.environ["GITHUB_RUN_ID"])
    base = os.environ["BACKEND_BASE"].rstrip("/")
    secret = os.environ["CRON_SECRET"]
    # Recheck immediately before writing, in case this job waited in a queue.
    capacity = check(base, secret)
    if not capacity["ready"]:
        print(json.dumps(capacity))
        return 1
    started = time.monotonic()
    req = Request(f"{base}/api/cron/{path}", method="POST",
                  headers={"Authorization": f"Bearer {secret}"})
    try:
        with urlopen(req, timeout=290) as response:
            status, raw = response.status, response.read(50000).decode()
    except HTTPError as exc:
        status, raw = exc.code, exc.read(50000).decode()
    # Never print headers or credentials. GitHub also masks its stored secret.
    raw = raw.replace(secret, "[REDACTED]")
    try:
        body = json.loads(raw)
    except ValueError:
        body = {"message": raw[:1500]}
    receipt = {"operation": operation, "http_status": status,
               "seconds": round(time.monotonic() - started, 2), "result": body}
    print(json.dumps(receipt))
    if body.get("skipped_count"):
        print("::warning::PARTIAL price coverage: unavailable tickers are listed above. "
              "This request completed, but does not authorize snapshot publication or schedule recovery.")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a") as stream:
            stream.write("## Bounded recovery\n\n```json\n" + json.dumps(receipt, indent=2)
                         + "\n```\n\nVerify actual dates, coverage and capacity before enabling schedules.\n")
    return 0 if status == 200 and result_ok(operation, body) else 1


if __name__ == "__main__":
    raise SystemExit(main())
