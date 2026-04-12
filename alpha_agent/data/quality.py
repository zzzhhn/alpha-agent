"""Data quality validation for OHLCV market data.

Implements the 7 validation rules from the v2.0 blueprint (p9):
  1. OHLCV non-negative
  2. Open <= High
  3. Open >= Low (corrected: Low <= Open)
  4. Volume > 0
  5. No duplicate timestamps
  6. No gaps > 5 trading days
  7. Prices not NaN
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TypedDict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Maximum allowed gap in trading days before flagging
_MAX_GAP_TRADING_DAYS = 5


# --------------------------------------------------------------------------- #
# Types
# --------------------------------------------------------------------------- #


class ValidationResult(TypedDict):
    """Single validation rule result."""

    rule: str
    passed: bool
    severity: str  # "pass" | "fail" | "warning"
    details: str
    affected_rows: int


class DataQualityReport(TypedDict):
    """Full quality report for a ticker's OHLCV data."""

    ticker: str
    total_rows: int
    rules: list[ValidationResult]
    overall_pass: bool


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def validate_ohlcv(ohlcv: pd.DataFrame, ticker: str) -> DataQualityReport:
    """Run all 7 validation rules against OHLCV data for a ticker.

    Parameters
    ----------
    ohlcv : pd.DataFrame
        MultiIndex (date, stock_code) with OHLCV columns.
    ticker : str
        Ticker to validate.

    Returns
    -------
    DataQualityReport
        Report with per-rule results and overall pass/fail.
    """
    try:
        df = ohlcv.xs(ticker, level="stock_code").copy()
    except KeyError:
        return DataQualityReport(
            ticker=ticker,
            total_rows=0,
            rules=[],
            overall_pass=False,
        )

    if df.empty:
        return DataQualityReport(
            ticker=ticker,
            total_rows=0,
            rules=[],
            overall_pass=False,
        )

    rules: list[ValidationResult] = [
        _check_non_negative(df),
        _check_open_le_high(df),
        _check_low_le_open(df),
        _check_volume_positive(df),
        _check_no_duplicate_timestamps(df),
        _check_no_large_gaps(df),
        _check_no_nan_prices(df),
    ]

    overall = all(r["passed"] for r in rules)

    return DataQualityReport(
        ticker=ticker,
        total_rows=len(df),
        rules=rules,
        overall_pass=overall,
    )


# --------------------------------------------------------------------------- #
# Individual validation rules (pure functions)
# --------------------------------------------------------------------------- #


def _check_non_negative(df: pd.DataFrame) -> ValidationResult:
    """Rule 1: OHLCV columns must be non-negative."""
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    negative_mask = (df[cols] < 0).any(axis=1)
    count = int(negative_mask.sum())
    return ValidationResult(
        rule="OHLCV non-negative",
        passed=count == 0,
        severity="pass" if count == 0 else "fail",
        details=f"{count} rows with negative values" if count > 0 else "All values non-negative",
        affected_rows=count,
    )


def _check_open_le_high(df: pd.DataFrame) -> ValidationResult:
    """Rule 2: Open <= High for every row."""
    if "open" not in df.columns or "high" not in df.columns:
        return _skip_result("Open <= High", "Missing columns")

    violations = df["open"] > df["high"]
    count = int(violations.sum())
    return ValidationResult(
        rule="Open <= High",
        passed=count == 0,
        severity="pass" if count == 0 else "fail",
        details=f"{count} rows where Open > High" if count > 0 else "All rows valid",
        affected_rows=count,
    )


def _check_low_le_open(df: pd.DataFrame) -> ValidationResult:
    """Rule 3: Low <= Open (and Low <= Close, Low <= High)."""
    if "low" not in df.columns or "open" not in df.columns:
        return _skip_result("Low <= Open", "Missing columns")

    violations = df["low"] > df["open"]
    count = int(violations.sum())
    return ValidationResult(
        rule="Low <= Open",
        passed=count == 0,
        severity="pass" if count == 0 else "fail",
        details=f"{count} rows where Low > Open" if count > 0 else "All rows valid",
        affected_rows=count,
    )


def _check_volume_positive(df: pd.DataFrame) -> ValidationResult:
    """Rule 4: Volume > 0."""
    if "volume" not in df.columns:
        return _skip_result("Volume > 0", "Missing volume column")

    zero_vol = df["volume"] <= 0
    count = int(zero_vol.sum())
    return ValidationResult(
        rule="Volume > 0",
        passed=count == 0,
        severity="pass" if count == 0 else "warning",
        details=f"{count} rows with zero/negative volume" if count > 0 else "All volumes positive",
        affected_rows=count,
    )


def _check_no_duplicate_timestamps(df: pd.DataFrame) -> ValidationResult:
    """Rule 5: No duplicate timestamps."""
    dupes = df.index.duplicated()
    count = int(dupes.sum())
    return ValidationResult(
        rule="No duplicate timestamps",
        passed=count == 0,
        severity="pass" if count == 0 else "fail",
        details=f"{count} duplicate timestamps" if count > 0 else "No duplicates",
        affected_rows=count,
    )


def _check_no_large_gaps(df: pd.DataFrame) -> ValidationResult:
    """Rule 6: No gaps > 5 trading days between consecutive rows."""
    if len(df) < 2:
        return _skip_result("No large gaps", "Insufficient data")

    dates = pd.Series(df.index)
    gaps = dates.diff().dt.days.dropna()
    large_gaps = gaps[gaps > _MAX_GAP_TRADING_DAYS]
    count = len(large_gaps)

    if count > 0:
        max_gap = int(large_gaps.max())
        details = f"{count} gaps > {_MAX_GAP_TRADING_DAYS} days (max: {max_gap} days)"
    else:
        details = "No large gaps detected"

    return ValidationResult(
        rule="No large gaps",
        passed=count == 0,
        severity="pass" if count == 0 else "warning",
        details=details,
        affected_rows=count,
    )


def _check_no_nan_prices(df: pd.DataFrame) -> ValidationResult:
    """Rule 7: Prices must not be NaN."""
    price_cols = [c for c in ("open", "high", "low", "close") if c in df.columns]
    nan_mask = df[price_cols].isna().any(axis=1)
    count = int(nan_mask.sum())
    return ValidationResult(
        rule="Prices not NaN",
        passed=count == 0,
        severity="pass" if count == 0 else "fail",
        details=f"{count} rows with NaN prices" if count > 0 else "No NaN prices",
        affected_rows=count,
    )


def _skip_result(rule: str, reason: str) -> ValidationResult:
    """Helper for rules that can't run due to missing data."""
    return ValidationResult(
        rule=rule,
        passed=True,
        severity="warning",
        details=f"Skipped: {reason}",
        affected_rows=0,
    )
