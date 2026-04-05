"""Backtest result metrics — immutable dataclass holding all alpha factor evaluation stats."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestResult:
    """Immutable container for backtest evaluation metrics.

    All fields are computed by :class:`BacktestEngine.run` and should never
    be mutated after creation.

    Attributes
    ----------
    ic_mean : float
        Mean Information Coefficient (Pearson correlation between factor
        values and forward 1-day returns, averaged across dates).
    ic_std : float
        Standard deviation of the IC time series.
    icir : float
        IC Information Ratio = ic_mean / ic_std.  Higher absolute values
        indicate a more consistent factor.
    rank_ic_mean : float
        Mean Spearman rank IC (rank correlation version of ic_mean).
    rank_icir : float
        Rank ICIR = rank_ic_mean / std(rank_ic_series).
    sharpe_ratio : float
        Annualised Sharpe ratio of the long-short quintile portfolio
        (assuming 252 trading days per year).
    annual_return : float
        Annualised mean return of the long-short portfolio.
    max_drawdown : float
        Maximum peak-to-trough drawdown of cumulative long-short returns.
        Always <= 0 (0 means no drawdown).
    turnover : float
        Average daily factor-rank turnover across all stocks and dates.
    alpha_decay : tuple[float, ...]
        Mean IC computed against forward returns at each lag in
        ``forward_periods`` (default: 1, 2, 3, 5, 10, 20 days).
    """

    ic_mean: float
    ic_std: float
    icir: float
    rank_ic_mean: float
    rank_icir: float
    sharpe_ratio: float
    annual_return: float
    max_drawdown: float
    turnover: float
    alpha_decay: tuple[float, ...]

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def summary_dict(self) -> dict[str, float | tuple[float, ...]]:
        """Return a plain dict of all fields (useful for serialisation)."""
        return {
            "ic_mean": self.ic_mean,
            "ic_std": self.ic_std,
            "icir": self.icir,
            "rank_ic_mean": self.rank_ic_mean,
            "rank_icir": self.rank_icir,
            "sharpe_ratio": self.sharpe_ratio,
            "annual_return": self.annual_return,
            "max_drawdown": self.max_drawdown,
            "turnover": self.turnover,
            "alpha_decay": self.alpha_decay,
        }

    def __str__(self) -> str:  # noqa: D105
        decay_str = ", ".join(f"{v:.4f}" for v in self.alpha_decay)
        return (
            f"BacktestResult(\n"
            f"  IC        = {self.ic_mean:+.4f} +/- {self.ic_std:.4f}  "
            f"(ICIR={self.icir:+.4f})\n"
            f"  Rank IC   = {self.rank_ic_mean:+.4f}  "
            f"(Rank ICIR={self.rank_icir:+.4f})\n"
            f"  Sharpe    = {self.sharpe_ratio:+.4f}\n"
            f"  Annual Ret= {self.annual_return:+.2%}\n"
            f"  Max DD    = {self.max_drawdown:+.2%}\n"
            f"  Turnover  = {self.turnover:.4f}\n"
            f"  Alpha Decay = [{decay_str}]\n"
            f")"
        )
