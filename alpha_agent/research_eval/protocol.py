"""Frozen design, not authorization to change any running account or strategy."""
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
import json
from typing import Sequence

from .metrics import calendar_dates


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date

    def __post_init__(self):
        if type(self.start) is not date or type(self.end) is not date or self.start > self.end:
            raise ValueError("invalid inclusive date range")


@dataclass(frozen=True)
class FrozenProtocol:
    version: str = "quant-p0-v1.0.0-20261111"
    frozen_on: date = date(2026, 11, 11)
    data_available: DateRange = DateRange(date(2023, 10, 30), date(2026, 10, 30))
    warmup: DateRange = DateRange(date(2023, 10, 30), date(2024, 10, 30))
    train: DateRange = DateRange(date(2024, 10, 31), date(2025, 6, 30))
    validation: tuple[DateRange, ...] = (
        DateRange(date(2025, 8, 1), date(2025, 10, 31)),
        DateRange(date(2025, 12, 2), date(2026, 2, 27)),
    )
    historical_test: DateRange = DateRange(date(2026, 4, 1), date(2026, 10, 30))
    historical_test_is_unseen: bool = False
    final_forward: DateRange = DateRange(date(2026, 11, 12), date(2027, 11, 12))
    horizons: tuple[int, ...] = (1, 3, 5, 20)
    # Auxiliary direction diagnostics: bullish >threshold, bearish <-threshold,
    # HOLD abs(return)<=threshold. None never becomes a hit. Not trade triggers.
    thresholds: tuple[float, ...] = (0.0, 0.005)
    purge_sessions: int = 21  # one entry delay plus max holding horizon
    embargo_sessions: int = 21
    l2_fee_bps: float = 10
    l2_extra_slippage_bps: float = 0  # existing comprehensive cost assumption
    bot_fee_bps: float = 10
    bot_slippage_bps: float = 5
    stress_total_bps: tuple[float, ...] = (10, 15, 20, 30)
    benchmarks: tuple[str, ...] = ("SPY", "cash_zero_interest", "RSP", "eligible_equal_weight")
    arms: tuple[str, ...] = ("tactical_v3", "strategic_v2", "bot_frozen_config", "ew_monthly", "momentum_12_1")
    primary_comparators: tuple[str, ...] = ("SPY", "eligible_equal_weight")
    family_size: int = 40  # 5 arms x 4 horizons x 2 comparators, upper bound
    family_alpha: float = 0.05
    primary_offset: int = 0
    minimum_forward_sessions: int = 252
    annual_sessions: int = 252
    cash_interest: float = 0

    def __post_init__(self):
        blocks = (self.train, *self.validation, self.historical_test, self.final_forward)
        if any(a.end >= b.start for a, b in zip(blocks, blocks[1:])):
            raise ValueError("splits must be chronological and disjoint")
        if (not self.version or not self.horizons or any(type(h) is not int or h < 1 for h in self.horizons)
                or len(set(self.horizons)) != len(self.horizons)):
            raise ValueError("invalid version or horizons")
        if self.purge_sessions < max(self.horizons)+1 or self.embargo_sessions < max(self.horizons)+1:
            raise ValueError("purge/embargo must cover entry delay plus horizon")
        if self.final_forward.start <= self.frozen_on:
            raise ValueError("forward data must follow registration")
        if self.family_size < len(self.arms)*len(self.horizons)*len(self.primary_comparators):
            raise ValueError("multiple-test family undercounted")

    def to_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self), default=lambda value: value.isoformat()))

    @property
    def fingerprint(self) -> str:
        return sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


PROTOCOL = FrozenProtocol()


def purged_training_dates(
    sessions: Sequence[date], training: DateRange, evaluation: DateRange, *,
    entry_delay: int = 1, horizon: int = 20, embargo: int = 21,
) -> tuple[date, ...]:
    """Expanding chronological folds only; no shuffled/stacked pseudo-history.

    Keep training decisions whose entire delayed label ends before evaluation
    and leave `embargo` whole sessions between decision blocks. Caller supplies
    a complete exchange calendar through all possible label endpoints.
    """
    days = calendar_dates(sessions)
    if training.end >= evaluation.start:
        raise ValueError("only training preceding evaluation is allowed")
    if any(type(value) is not int for value in (entry_delay, horizon, embargo)) or min(entry_delay, embargo) < 0 or horizon < 1:
        raise ValueError("invalid delay/horizon/embargo")
    evaluation_indices = [i for i, day in enumerate(days) if evaluation.start <= day <= evaluation.end]
    if not evaluation_indices:
        raise ValueError("evaluation absent from calendar")
    first = evaluation_indices[0]
    return tuple(day for i, day in enumerate(days)
                 if training.start <= day <= training.end
                 and i + entry_delay + horizon < first and i + embargo < first)
