"""Bounded local-search candidate generation for the methodology proposer.
Each candidate is a single-knob delta from the current config (one change at a
time keeps attribution clean and the trial count small for honest deflation)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfigDelta:
    key: str
    new_value: Any
    rationale: str


def enumerate_candidates(current: dict[str, Any]) -> list[ConfigDelta]:
    out: list[ConfigDelta] = []

    band = float(current.get("rating.no_trade_band", 0.15))
    for nb in (round(band - 0.05, 4), round(band + 0.05, 4)):
        if 0.0 <= nb <= 0.5:
            out.append(ConfigDelta("rating.no_trade_band", nb,
                                   f"no-trade band {band} to {nb}"))

    thr = current.get(
        "rating.tier_thresholds",
        {"buy": 1.5, "ow": 0.5, "hold": -0.5, "uw": -1.5},
    )
    for nb in (round(thr["buy"] - 0.1, 4), round(thr["buy"] + 0.1, 4)):
        out.append(ConfigDelta("rating.tier_thresholds", {**thr, "buy": nb},
                               f"BUY threshold {thr['buy']} to {nb}"))

    mode = current.get("factor.mode", "short")
    out.append(ConfigDelta("factor.mode", "long" if mode == "short" else "short",
                           f"factor mode {mode} flip"))

    ic = float(current.get("signal.ic_accept_threshold", 0.02))
    for nv in (round(ic - 0.01, 4), round(ic + 0.01, 4)):
        if nv > 0:
            out.append(ConfigDelta("signal.ic_accept_threshold", nv,
                                   f"IC-accept {ic} to {nv}"))

    return out[:8]  # hard cap on trials per day
