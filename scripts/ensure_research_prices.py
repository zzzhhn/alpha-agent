"""Bounded price-before-research dependency; never computes signals or trades."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

if __package__:
    from .cron_preflight import check
else:
    from cron_preflight import check


def within_research_day(day: str, now: datetime | None = None) -> bool:
    instant = now or datetime.now(UTC)
    deadline = datetime.combine(datetime.fromisoformat(day).date() + timedelta(days=1), time(), UTC)
    return instant.date().isoformat() == day and (deadline - instant).total_seconds() >= 300


def ensure_prices(request, capacity_check, *, research_day: str | None = None) -> dict:
    receipt = request("research_readiness")
    if receipt.get("ok") is not True:
        raise RuntimeError("Invalid research readiness response")
    if receipt.get("ready") is True:
        return receipt
    count = receipt.get("price_universe_count", 0)
    if not isinstance(count, int) or not 1 <= count <= 600:
        raise RuntimeError("Price recovery universe outside bounded scope")
    partial_errors = 0
    for offset in range(0, count, 75):
        if research_day and not within_research_day(research_day):
            return {**receipt, "ready": False, "reason": "research_day_window_ended"}
        capacity = capacity_check()
        if not capacity.get("ready"):
            if not capacity.get("expected_pause"):
                raise RuntimeError("Service preflight failed unexpectedly")
            return {**receipt, "ready": False, "reason": "service_or_storage_paused"}
        result = request(f"daily_prices?limit=75&offset={offset}&period=5d", write=True)
        if "updated" not in result:
            raise RuntimeError("Invalid daily price response")
        partial_errors += result.get("error_count", 0)
    receipt = request("research_readiness")
    if receipt.get("ok") is not True:
        raise RuntimeError("Invalid research readiness response")
    if not receipt.get("ready"):
        receipt["reason"] = "awaiting_current_market_prices"
    receipt["partial_price_errors"] = partial_errors
    return receipt


def main() -> int:
    base = os.environ["BACKEND_BASE"].rstrip("/")
    secret = os.environ["CRON_SECRET"]
    research_day = datetime.now(UTC).date().isoformat()

    def request(path, write=False):
        req = Request(f"{base}/api/cron/{path}", method="POST" if write else "GET",
                      headers={"Authorization": f"Bearer {secret}"})
        with urlopen(req, timeout=290) as response:
            # Log only structured non-sensitive operational receipt, not raw
            # exceptions, auth headers, arbitrary provider responses or keys.
            return json.loads(response.read(50000))

    try:
        receipt = ensure_prices(request, lambda: check(base, secret), research_day=research_day)
    except Exception as exc:
        print(json.dumps({"ready": False, "error_type": type(exc).__name__}))
        return 1
    if not within_research_day(research_day):
        receipt.update(ready=False, reason="research_day_window_ended")
    print(json.dumps(receipt))
    ready = receipt.get("ready") is True
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a") as stream:
            stream.write(f"ready={'true' if ready else 'false'}\n")
            stream.write(f"research_day={research_day}\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a") as stream:
            stream.write("## Research price readiness\n\n```json\n" + json.dumps(receipt, indent=2) + "\n```\n")
    if not ready:
        print("::warning::Research refresh paused: current price coverage is not ready. No signals or snapshot published.")
    elif receipt.get("partial_price_errors"):
        print("::warning::Partial price-source errors recorded; actual research coverage and benchmark gate passed.")
    return 0 if ready or os.environ.get("TRIGGER_EVENT") == "schedule" else 1


if __name__ == "__main__":
    raise SystemExit(main())
