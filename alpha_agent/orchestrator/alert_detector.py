"""Alert trigger detection. Pure function: given prev + curr RatingCard
dicts, returns a list of alert dicts (type, payload). The cron handler
enqueues these to alert_queue with the appropriate dedup_bucket."""
from __future__ import annotations

from typing import Any


def _find_signal(card: dict, name: str) -> dict | None:
    for b in card.get("breakdown", []):
        if b.get("signal") == name:
            return b
    return None


def detect_alerts(
    prev: dict | None,
    curr: dict,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    # 1. rating_change
    if prev is not None and prev.get("rating") != curr.get("rating"):
        alerts.append({
            "type": "rating_change",
            "payload": {
                "from": prev["rating"], "to": curr["rating"],
                "composite_from": prev.get("composite_score"),
                "composite_to": curr.get("composite_score"),
            },
        })

    # 2. gap_3sigma (premarket signal)
    pm = _find_signal(curr, "premarket")
    if pm and abs(pm.get("z", 0)) > 3.0:
        alerts.append({
            "type": "gap_3sigma",
            "payload": {"gap_sigma": pm["z"], "raw": pm.get("raw")},
        })

    # 3. iv_spike (options signal)
    opt = _find_signal(curr, "options")
    if opt:
        iv_pct = (opt.get("raw") or {}).get("iv_percentile", 0)
        if iv_pct > 90:
            alerts.append({
                "type": "iv_spike",
                "payload": {"iv_percentile": iv_pct},
            })

    # 4. news_velocity (news signal — count > 3× historical mean)
    news = _find_signal(curr, "news")
    if news:
        n = (news.get("raw") or {}).get("n", 0)
        if n >= 10:  # placeholder threshold; M3 uses moving average
            alerts.append({
                "type": "news_velocity",
                "payload": {"n_24h": n},
            })

    return alerts
