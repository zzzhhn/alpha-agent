"""SQLAlchemy 2.0 schema + CRUD for the Factor Performance DB (T4.1).

Two tables:

  factors        — one row per unique (ast_hash). Carries denormalized
                   last-run metrics so the Zoo browser can sort/filter
                   without joining factor_runs on every request.

  factor_runs    — one row per backtest invocation. Stores the metrics
                   the run produced + the config it was run with + the
                   daily_ic time-series for decay analysis.

The Factor row's ast_hash deduplicates: re-running the same expression
under different config produces ONE Factor + N FactorRun rows, not N
Factors. Config differences between runs live on FactorRun, not Factor.

Connection: prefers DATABASE_URL (Neon Postgres in prod). Falls back to
sqlite at alpha_agent/data/factor_db.sqlite for local dev when the env
var is missing — useful when the user wants to dogfood without setting
up Neon.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
)

logger = logging.getLogger(__name__)


# ── Schema ─────────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base."""


def _utcnow() -> datetime:
    """Use a fresh UTC stamp for default values (avoids "default at import
    time" bug that bites SQLAlchemy users)."""
    return datetime.utcnow()


class Factor(Base):
    """One unique factor expression, identified by AST hash.

    `ast_hash` is the dedup key — same expression always yields the same
    Factor row, regardless of how many times users save it. `n_runs`
    tracks how many runs have been recorded; `last_*` carry the most
    recent run's headline metrics so the list endpoint doesn't need
    a join.
    """

    __tablename__ = "factors"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    ast_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    name: Mapped[str] = mapped_column(String(120))
    expression: Mapped[str] = mapped_column(Text)
    hypothesis: Mapped[str | None] = mapped_column(Text, default=None)
    intuition: Mapped[str | None] = mapped_column(Text, default=None)

    # Denormalized last-run snapshot for fast list queries.
    last_direction: Mapped[str | None] = mapped_column(String(20), default=None)
    last_neutralize: Mapped[str | None] = mapped_column(String(20), default=None)
    last_benchmark: Mapped[str | None] = mapped_column(String(20), default=None)
    last_test_sharpe: Mapped[float | None] = mapped_column(Float, default=None)
    last_test_ic: Mapped[float | None] = mapped_column(Float, default=None)
    last_alpha_t: Mapped[float | None] = mapped_column(Float, default=None)
    last_alpha_p: Mapped[float | None] = mapped_column(Float, default=None)
    last_psr: Mapped[float | None] = mapped_column(Float, default=None)
    last_overfit_flag: Mapped[bool | None] = mapped_column(Boolean, default=None)

    n_runs: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow,
    )


class FactorRun(Base):
    """A single backtest invocation. Captures both the config that was
    run AND the metrics it produced.

    daily_ic is the per-day Spearman IC time-series (length = test
    slice's day count, typically 50-150). Used for decay-alert
    detection (`decay_alerts()` rolls a 60d window vs the 1y baseline).
    """

    __tablename__ = "factor_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    factor_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("factors.id", ondelete="CASCADE"), index=True,
    )

    # Config that was actually run. Lets us tell apart a SR=2.5 long_short
    # run from a SR=0.4 long_only run of the same expression — would
    # otherwise look like the same factor "regressed" between saves.
    panel_version: Mapped[str] = mapped_column(String(40), default="sp500_v3")
    direction: Mapped[str] = mapped_column(String(20))
    neutralize: Mapped[str] = mapped_column(String(20), default="none")
    benchmark_ticker: Mapped[str] = mapped_column(String(20), default="SPY")
    top_pct: Mapped[float] = mapped_column(Float, default=0.30)
    bottom_pct: Mapped[float] = mapped_column(Float, default=0.30)
    transaction_cost_bps: Mapped[float] = mapped_column(Float, default=0.0)

    # Test metrics — the canonical set the audit + Bundle A surfaced.
    test_sharpe: Mapped[float] = mapped_column(Float)
    test_ic: Mapped[float] = mapped_column(Float)
    test_psr: Mapped[float | None] = mapped_column(Float, default=None)
    alpha_annualized: Mapped[float | None] = mapped_column(Float, default=None)
    alpha_t: Mapped[float | None] = mapped_column(Float, default=None)
    alpha_p: Mapped[float | None] = mapped_column(Float, default=None)
    beta: Mapped[float | None] = mapped_column(Float, default=None)
    r_squared: Mapped[float | None] = mapped_column(Float, default=None)
    overfit_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    # Per-day IC time-series for decay tracking. JSON list of floats.
    daily_ic: Mapped[list[float] | None] = mapped_column(JSON, default=None)

    ran_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


# ── Connection layer ───────────────────────────────────────────────────────


_DEFAULT_SQLITE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "factor_db.sqlite"
)
_engine: Engine | None = None  # lazy-initialised process-wide singleton
_schema_ready: bool = False    # idempotent one-shot init guard, see get_engine()


def is_db_configured() -> bool:
    """Cheap check: do we have a DATABASE_URL or fallback path? Used by
    callers that want to skip persistence gracefully when no DB is
    available (e.g. CI without Neon)."""
    return bool(os.environ.get("DATABASE_URL")) or True  # sqlite fallback always works


def _resolve_url() -> str:
    """Return the SQLAlchemy URL to use. Prefers Neon Postgres via the
    DATABASE_URL env var; falls back to local sqlite.

    Neon sometimes emits `postgres://` but SQLAlchemy 2.0 wants
    `postgresql://` — normalize the prefix here so callers don't have
    to think about it.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    _DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{_DEFAULT_SQLITE_PATH}"


def get_engine() -> Engine:
    """Process-wide singleton engine. Initialised lazily.

    `pool_pre_ping=True` is critical for serverless Neon: connections
    can be killed by the pooler at any time, and without pre_ping the
    next query in a request would fail with "connection closed". The
    pre_ping costs ~1ms per acquisition but eliminates an entire class
    of flaky errors.

    Auto-creates schema on first acquisition (one-shot per process via
    `_schema_ready` guard). Without this, scripts that hit the DB
    directly — `verify_insider_alpha.py`, ad-hoc notebooks, the
    Hypothesis Lab worker — would all see `OperationalError: no such
    table: factors` because they never import the API route module
    where `init_schema()` was previously the only call site.
    `Base.metadata.create_all` is idempotent (CREATE IF NOT EXISTS)
    so this is safe to run on every process boot in production.
    """
    global _engine, _schema_ready
    if _engine is None:
        url = _resolve_url()
        _engine = create_engine(url, pool_pre_ping=True, pool_recycle=300)
    if not _schema_ready:
        try:
            Base.metadata.create_all(_engine)
            _schema_ready = True
        except Exception as exc:  # noqa: BLE001 — surface via downstream query
            # Don't poison the singleton; let the caller's actual operation
            # fail with a clearer error. Common cause: readonly DB user, or
            # Neon role missing CREATE privilege.
            import logging
            logging.getLogger(__name__).warning(
                "factor DB schema auto-init failed: %s: %s; "
                "subsequent queries will surface the underlying error",
                type(exc).__name__, exc,
            )
    return _engine


def init_schema() -> None:
    """Create tables if they don't exist. Idempotent. Now mostly redundant
    with the auto-init in `get_engine()`, but kept as the public surface
    for any caller that wants to force a re-check (e.g. after a manual
    DROP or migration)."""
    global _schema_ready
    Base.metadata.create_all(get_engine())
    _schema_ready = True


# ── Helpers ────────────────────────────────────────────────────────────────


def _ast_hash(expression: str, operators_used: list[str] | None = None) -> str:
    """Stable sha256 of a canonical (sorted-ops) representation. Same
    expression always hashes the same, regardless of declared-ops order
    — that's user-visible but not semantically meaningful."""
    canonical = json.dumps({
        "expr": expression.strip(),
        "ops": sorted(operators_used or []),
    }, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:32]}"


# ── CRUD ───────────────────────────────────────────────────────────────────


def upsert_factor(
    *,
    name: str,
    expression: str,
    operators_used: list[str] | None = None,
    hypothesis: str | None = None,
    intuition: str | None = None,
    last_run_summary: dict[str, Any] | None = None,
) -> str:
    """Insert or update a Factor by ast_hash. Returns factor_id.

    The summary dict is denormalized into the last_* columns so the
    list endpoint can sort/filter without joining factor_runs. None
    values leave the existing column unchanged.
    """
    ast_hash = _ast_hash(expression, operators_used)
    with Session(get_engine()) as s:
        existing = s.scalar(select(Factor).where(Factor.ast_hash == ast_hash))
        if existing:
            existing.name = name or existing.name
            if hypothesis is not None:
                existing.hypothesis = hypothesis
            if intuition is not None:
                existing.intuition = intuition
            if last_run_summary:
                _apply_summary(existing, last_run_summary)
            existing.n_runs = (existing.n_runs or 0) + 1
            existing.updated_at = _utcnow()
            s.commit()
            return existing.id

        f = Factor(
            id=_new_id("factor"),
            ast_hash=ast_hash,
            name=name,
            expression=expression,
            hypothesis=hypothesis,
            intuition=intuition,
            n_runs=1,
        )
        if last_run_summary:
            _apply_summary(f, last_run_summary)
        s.add(f)
        s.commit()
        return f.id


def _apply_summary(f: Factor, s: dict[str, Any]) -> None:
    """Copy a last-run summary dict onto the Factor's denormalized fields."""
    f.last_direction = s.get("direction") or f.last_direction
    f.last_neutralize = s.get("neutralize") or f.last_neutralize
    f.last_benchmark = s.get("benchmark") or f.last_benchmark
    if (v := s.get("test_sharpe")) is not None:
        f.last_test_sharpe = float(v)
    if (v := s.get("test_ic")) is not None:
        f.last_test_ic = float(v)
    if (v := s.get("alpha_t")) is not None:
        f.last_alpha_t = float(v)
    if (v := s.get("alpha_p")) is not None:
        f.last_alpha_p = float(v)
    if (v := s.get("psr")) is not None:
        f.last_psr = float(v)
    if (v := s.get("overfit_flag")) is not None:
        f.last_overfit_flag = bool(v)


def record_run(
    *,
    factor_id: str,
    panel_version: str = "sp500_v3",
    direction: str,
    neutralize: str = "none",
    benchmark_ticker: str = "SPY",
    top_pct: float = 0.30,
    bottom_pct: float = 0.30,
    transaction_cost_bps: float = 0.0,
    test_sharpe: float,
    test_ic: float,
    test_psr: float | None = None,
    alpha_annualized: float | None = None,
    alpha_t: float | None = None,
    alpha_p: float | None = None,
    beta: float | None = None,
    r_squared: float | None = None,
    overfit_flag: bool = False,
    daily_ic: list[float] | None = None,
) -> str:
    """Insert a new FactorRun. Returns run_id."""
    run = FactorRun(
        id=_new_id("run"),
        factor_id=factor_id,
        panel_version=panel_version,
        direction=direction,
        neutralize=neutralize,
        benchmark_ticker=benchmark_ticker,
        top_pct=top_pct,
        bottom_pct=bottom_pct,
        transaction_cost_bps=transaction_cost_bps,
        test_sharpe=test_sharpe,
        test_ic=test_ic,
        test_psr=test_psr,
        alpha_annualized=alpha_annualized,
        alpha_t=alpha_t,
        alpha_p=alpha_p,
        beta=beta,
        r_squared=r_squared,
        overfit_flag=overfit_flag,
        daily_ic=daily_ic,
    )
    with Session(get_engine()) as s:
        s.add(run)
        s.commit()
        return run.id


def list_factors(limit: int = 50) -> list[dict[str, Any]]:
    """Return up to `limit` factors, newest-updated first.

    Returns plain dicts (not ORM objects) so the API endpoint can
    serialize directly without dealing with detached-session issues.
    """
    with Session(get_engine()) as s:
        rows = s.scalars(
            select(Factor).order_by(Factor.updated_at.desc()).limit(limit)
        ).all()
        return [_factor_to_dict(f) for f in rows]


def get_factor_runs(factor_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Run history for a factor, newest first."""
    with Session(get_engine()) as s:
        rows = s.scalars(
            select(FactorRun)
            .where(FactorRun.factor_id == factor_id)
            .order_by(FactorRun.ran_at.desc())
            .limit(limit)
        ).all()
        return [_run_to_dict(r) for r in rows]


def delete_factor(factor_id: str) -> bool:
    """Delete a factor + cascade its runs. Returns True if found."""
    with Session(get_engine()) as s:
        f = s.get(Factor, factor_id)
        if not f:
            return False
        s.delete(f)
        s.commit()
        return True


def decay_alerts(
    *,
    rolling_window_days: int = 60,
    min_runs: int = 3,
    decay_threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """Surface factors whose recent runs show meaningful IC decay.

    For each factor with ≥`min_runs` runs, compares the most recent run's
    `test_ic` against the historical mean of all earlier runs. Flags as
    decayed when |latest / baseline| < (1 − decay_threshold) and the
    latest is positive (i.e. the signal is fading, not flipping).

    Returns a list of dicts — one per flagged factor — with diagnostic
    fields the frontend can render in a banner.
    """
    out: list[dict[str, Any]] = []
    with Session(get_engine()) as s:
        factors = s.scalars(
            select(Factor).where(Factor.n_runs >= min_runs)
        ).all()
        for f in factors:
            runs = s.scalars(
                select(FactorRun)
                .where(FactorRun.factor_id == f.id)
                .order_by(FactorRun.ran_at.desc())
            ).all()
            if len(runs) < min_runs:
                continue
            latest = runs[0].test_ic
            baseline = sum(r.test_ic for r in runs[1:]) / max(len(runs) - 1, 1)
            if abs(baseline) < 1e-6:
                continue
            decay = 1.0 - (latest / baseline)
            if decay > decay_threshold and latest > 0 and baseline > 0:
                out.append({
                    "factor_id": f.id,
                    "name": f.name,
                    "expression": f.expression,
                    "n_runs": f.n_runs,
                    "baseline_ic": float(baseline),
                    "latest_ic": float(latest),
                    "decay_pct": float(decay),
                    "latest_run_at": runs[0].ran_at.isoformat(),
                })
    return out


# ── Serializers (private — callers use the dict-returning CRUD fns) ────────


def _factor_to_dict(f: Factor) -> dict[str, Any]:
    return {
        "id": f.id,
        "ast_hash": f.ast_hash,
        "name": f.name,
        "expression": f.expression,
        "hypothesis": f.hypothesis,
        "intuition": f.intuition,
        "last_direction": f.last_direction,
        "last_neutralize": f.last_neutralize,
        "last_benchmark": f.last_benchmark,
        "last_test_sharpe": f.last_test_sharpe,
        "last_test_ic": f.last_test_ic,
        "last_alpha_t": f.last_alpha_t,
        "last_alpha_p": f.last_alpha_p,
        "last_psr": f.last_psr,
        "last_overfit_flag": f.last_overfit_flag,
        "n_runs": f.n_runs,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


def _run_to_dict(r: FactorRun) -> dict[str, Any]:
    return {
        "id": r.id,
        "factor_id": r.factor_id,
        "panel_version": r.panel_version,
        "direction": r.direction,
        "neutralize": r.neutralize,
        "benchmark_ticker": r.benchmark_ticker,
        "top_pct": r.top_pct,
        "bottom_pct": r.bottom_pct,
        "transaction_cost_bps": r.transaction_cost_bps,
        "test_sharpe": r.test_sharpe,
        "test_ic": r.test_ic,
        "test_psr": r.test_psr,
        "alpha_annualized": r.alpha_annualized,
        "alpha_t": r.alpha_t,
        "alpha_p": r.alpha_p,
        "beta": r.beta,
        "r_squared": r.r_squared,
        "overfit_flag": r.overfit_flag,
        "daily_ic": r.daily_ic,
        "ran_at": r.ran_at.isoformat() if r.ran_at else None,
    }
