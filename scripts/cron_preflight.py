"""Read-only cron smoke test; never retries, writes data or triggers a job."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def check(base: str, secret: str) -> dict:
    if not secret:
        return {"ready": False, "reason": "missing_cron_secret", "expected_pause": False}
    request = Request(
        base.rstrip("/") + "/api/cron/preflight",
        headers={"Authorization": f"Bearer {secret}"},
    )
    try:
        with urlopen(request, timeout=25) as response:
            # The endpoint is a small aggregate, not a data export.
            payload = json.loads(response.read(8192))
    except HTTPError as exc:
        return {"ready": False, "reason": f"http_{exc.code}",
                "expected_pause": exc.code in (402, 429, 503)}
    except (URLError, TimeoutError):
        return {"ready": False, "reason": "service_unreachable", "expected_pause": True}
    except (ValueError, OSError):
        return {"ready": False, "reason": "invalid_preflight_response", "expected_pause": False}
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return {"ready": False, "reason": "invalid_preflight_response", "expected_pause": False}
    if payload.get("allow_writes") is True:
        return {"ready": True, "reason": "storage_check_passed", "expected_pause": False,
                "database_bytes": payload.get("database_bytes"),
                "budget_bytes": payload.get("budget_bytes")}
    paused = payload.get("reason") == "storage_headroom_low"
    return {"ready": False, "reason": "storage_headroom_low" if paused else "invalid_preflight_response",
            "expected_pause": paused}


def finish(result: dict, *, scheduled: bool) -> int:
    ready = result["ready"]
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a") as stream:
            stream.write(f"ready={'true' if ready else 'false'}\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a") as stream:
            stream.write(
                f"## Cron preflight: {'ready' if ready else 'PAUSED, no work executed'}\n\n"
                f"Reason: `{result['reason']}`. This is a read-only capacity check, "
                "not proof of data freshness, provider quota or strategy performance.\n"
            )
    print(json.dumps(result))
    if ready:
        return 0
    # Known infrastructure/quota pauses skip scheduled business jobs. Auth,
    # schema and application defects remain failures, as do ALL manual probes.
    if scheduled and result["expected_pause"]:
        print(f"::warning::Scheduled work paused: {result['reason']}; no ingestion executed")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(finish(check(
        os.environ.get("BACKEND_BASE", "https://alpha-api.bobbyzhong.com"),
        os.environ.get("CRON_SECRET", ""),
    ), scheduled=os.environ.get("TRIGGER_EVENT") == "schedule"))
