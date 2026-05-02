"""Survivorship-bias correction via point-in-time index membership.

Source: fja05680/sp500 GitHub repo (MIT-licensed, last refreshed 2026-01-17).
The CSV `sp500_membership_2026-01-17.csv` (committed to alpha_agent/data/) has
schema `date, tickers` where each row is a snapshot of the SP500 constituent
list as of that date. A new row appears whenever membership changed.

For any panel date `t`, the SP500 membership at `t` is the snapshot from the
latest row with `snapshot_date <= t`. Panel dates after the CSV's last entry
inherit the most recent snapshot (acceptable: SP100 / mega-cap tickers
rarely churn, and the lag is bounded by the CSV refresh cadence).

Public API:
    load_membership_history(csv_path) -> list[(date, frozenset[str])]
    build_is_member_mask(panel_dates, panel_tickers) -> np.ndarray  (T, N) bool

The mask is consumed by `factor_backtest._load_panel()` and applied inside
`kernel.evaluate_factor_full()` — non-member cells get NaN'd before any
cross-sectional rank, so they cannot enter long/short baskets and cannot
contaminate IC.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

_DEFAULT_CSV = (
    Path(__file__).resolve().parent / "sp500_membership_2026-01-17.csv"
)


def _normalize_ticker(t: str) -> str:
    """Convert fja's dot-form (BRK.B) to Yahoo's dash-form (BRK-B).

    yfinance uses dash for class shares; fja05680 uses dot. Both refer to the
    same security. Normalizing to Yahoo's form keeps the panel's index space
    unchanged.
    """
    return t.replace(".", "-")


def load_membership_history(
    csv_path: Path | str | None = None,
) -> list[tuple[pd.Timestamp, frozenset[str]]]:
    """Parse the fja05680 snapshot CSV into a sorted list of (date, ticker_set).

    Returns an empty list if the file is missing — caller decides whether to
    fall back to "everything is a member" (lookahead-biased) or to fail.
    """
    path = Path(csv_path) if csv_path else _DEFAULT_CSV
    if not path.exists():
        return []

    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    history: list[tuple[pd.Timestamp, frozenset[str]]] = []
    for _, row in df.iterrows():
        raw = str(row["tickers"])
        members = frozenset(
            _normalize_ticker(t.strip())
            for t in raw.split(",")
            if t.strip()
        )
        history.append((row["date"], members))
    return history


def build_is_member_mask(
    panel_dates: np.ndarray,
    panel_tickers: tuple[str, ...] | list[str],
    csv_path: Path | str | None = None,
) -> np.ndarray | None:
    """Build a (T, N) boolean mask: True iff ticker n was an SP500 member on date t.

    Args:
        panel_dates: shape (T,) array of "YYYY-MM-DD" strings.
        panel_tickers: length-N sequence of ticker symbols (Yahoo form).
        csv_path: override the default fja05680 CSV location.

    Returns:
        (T, N) bool ndarray, or None if the CSV is missing (caller falls back
        to no-mask behavior with a warning).

    Edge cases:
        * Panel dates before the earliest snapshot → that snapshot's set
          (rare in practice; CSV starts 1996-01-02).
        * Panel dates after the last snapshot → the last snapshot's set
          (acceptable when CSV refresh lag < panel tail length).
        * Panel ticker never in any snapshot → all-False column for that
          ticker, with a stderr warning (catches typos / non-SP500 tickers).
    """
    history = load_membership_history(csv_path)
    if not history:
        return None

    snap_dates = np.array([d.to_datetime64() for d, _ in history])
    panel_dates_dt = np.array(
        pd.to_datetime(panel_dates).to_numpy(), dtype="datetime64[ns]"
    )

    # For each panel date, find the largest snap_date index s.t. snap_date <= panel_date.
    # searchsorted with side="right" returns insertion point that keeps existing
    # elements <= target. Subtracting 1 gives the last such row.
    snap_idx = np.searchsorted(snap_dates, panel_dates_dt, side="right") - 1
    # Panel dates strictly before the first snapshot → use snap[0] (clip to 0,
    # not -1; better to over-include than to all-False them).
    snap_idx = np.clip(snap_idx, 0, len(history) - 1)

    T = len(panel_dates)
    N = len(panel_tickers)
    mask = np.zeros((T, N), dtype=bool)

    # Group rows by snap_idx so we hit each snapshot's set once, not T times.
    unique_snaps = np.unique(snap_idx)
    never_seen: set[str] = set(panel_tickers)
    for s in unique_snaps:
        members = history[int(s)][1]
        rows = np.where(snap_idx == s)[0]
        for n, tk in enumerate(panel_tickers):
            if tk in members:
                mask[rows, n] = True
                never_seen.discard(tk)

    if never_seen:
        warnings.warn(
            f"build_is_member_mask: {len(never_seen)} panel ticker(s) never "
            f"appear in any SP500 snapshot — they will be excluded from every "
            f"cross-section. Tickers: {sorted(never_seen)[:10]}"
            + (f" ... +{len(never_seen)-10} more" if len(never_seen) > 10 else ""),
            stacklevel=2,
        )

    return mask
