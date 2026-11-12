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
    baseline_initial_capital: float = 1_000_000
    baseline_rebalance: str = "month_end_d1_close"
    baseline_max_position: float = 0.02
    baseline_rebalance_turnover_cap: float = 0.20
    baseline_initial_turnover_cap: float = 1.0
    momentum_lookback_sessions: int = 252
    momentum_skip_sessions: int = 21
    momentum_top_n: int = 50
    baseline_shares: str = "integer_sell_first_cash_constrained"
    baseline_tie_break: str = "ticker_ascending"

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


# v1.0.0 stays importable and byte-identical (fingerprint b56a596c…) as the
# archived registration. It must never be edited; later versions are new
# objects so earlier evaluation outputs remain reproducible.
PROTOCOL_V1_0_0 = FrozenProtocol()


@dataclass(frozen=True)
class FactorRegime:
    """Live factor configuration in force for a protocol version's forward window."""
    expression: str
    panel: str
    effective_after: date  # first forward session evaluated under this expression
    previous_expression: str
    previous_panel: str
    approval: str


@dataclass(frozen=True)
class FrozenProtocolV11(FrozenProtocol):
    """v1.1.0: the user-approved restore of the live factor to its preset.

    All evaluation rules are unchanged from v1.0.0. Only the registration date,
    the forward window and the recorded factor regime differ. Samples from the
    v1.0.0 window (custom volume expression on the frozen research parquet) and
    this window must not be spliced into one forward record.
    """
    version: str = "quant-p0-v1.1.0-20261112"
    frozen_on: date = date(2026, 11, 12)
    # First XNYS session after the restore can take effect (signals computed
    # after the 2026-11-12 close); 252 sessions end on 2027-11-15.
    final_forward: DateRange = DateRange(date(2026, 11, 13), date(2027, 11, 15))
    factor_regime: FactorRegime = FactorRegime(
        expression="subtract(rank(ts_mean(returns, 12)), rank(ts_std(returns, 60)))",
        panel="live_daily_prices",
        effective_after=date(2026, 11, 12),
        previous_expression="group_neutralize(zscore(ts_zscore(volume,20)),sector)",
        previous_panel="frozen_research_parquet",
        approval="user-approved 2026-11-12; restore via admin endpoint, journaled in config_change_log",
    )
    supersedes: str = "quant-p0-v1.0.0-20261111"
    splice_with_superseded: bool = False


PROTOCOL = FrozenProtocolV11()
PROTOCOLS = {p.version: p for p in (PROTOCOL_V1_0_0, PROTOCOL)}


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
