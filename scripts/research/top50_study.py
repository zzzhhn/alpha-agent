"""Deterministic, local-only exploratory study. No DB, network, or live writes.

All statistical functions below accept in-memory objects. Only load_inputs(),
load_bundle(), and main() perform IO. Output contains aggregates, never rows.
This study is NOT one of the frozen protocol's 40 confirmatory tests.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import floor, sqrt
from pathlib import Path
import time
from unittest.mock import patch

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from alpha_agent.research_eval.metrics import calendar_dates, nav_from_returns
from alpha_agent.research_eval.protocol import PROTOCOL, DateRange, purged_training_dates
from alpha_agent.research_eval.statistics import newey_west
from alpha_agent.signals.registry import SIGNAL_REGISTRY

ROOT = Path(__file__).resolve().parents[2]
COSTS = (10, 15, 20, 30)
LIVE_H = (1, 5, 20)
FACTOR_H = (5, 20, 60)
FACTORS = ("preset_12d_minus_vol60", "momentum_12_1", "low_vol60", "pit_gross_profit_assets")
RULES = ("top50", "factor_analyst_positive", "coverage_ge_0.8", "buy40_hold80")


def xnys_sessions(start, end):
    cal = xcals.get_calendar("XNYS", start=str(start), end=str(end))
    idx = cal.sessions_in_range(str(start), str(end)).tz_localize(None)
    calendar_dates(tuple(d.date() for d in idx))
    return idx, cal


def identity_mask(index, columns):
    mask = pd.DataFrame(True, index=index, columns=columns)
    if "PARA" in columns:
        mask.loc[mask.index > pd.Timestamp("2025-08-06"), "PARA"] = False
    return mask


def forward_returns(prices, horizon, *, clean=True, block_end=None):
    """D+1 close -> D+1+h close, NEVER next available row.

    Caller must supply a complete session index. A missing intervening mark
    blocks the label. Clean sensitivity also blocks any >35% daily move from
    decision through exit (including the entry-day action). PARA identity is
    excluded in both modes. No future-validity filter changes a decision set.
    """
    if horizon < 1 or prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("invalid horizon/calendar")
    p = prices.where(identity_mask(prices.index, prices.columns))
    p = p.where(p > 0)
    result = p.shift(-(horizon + 1)) / p.shift(-1) - 1
    good = p.notna().astype(int).rolling(horizon + 1).sum().shift(-(horizon + 1))
    result = result.where(good.eq(horizon + 1))
    if clean:
        jumps = p.pct_change(fill_method=None).abs().gt(0.35)
        bad = jumps.astype(int).rolling(horizon + 1).sum().shift(-(horizon + 1))
        result = result.where(bad.eq(0))
    if block_end is not None:
        ends = pd.Series(prices.index, index=prices.index).shift(-(horizon + 1))
        result.loc[ends.isna() | ends.gt(pd.Timestamp(block_end))] = np.nan
    return result


def round_trip_net(gross, bps):
    """One unit bought; exit sell notional = 1+gross, matching metrics helper."""
    if not np.isfinite(gross):
        return np.nan
    return nav_from_returns([gross], [1.0], [1.0 + gross], fee_bps=bps).net_returns[0]


def pit_quality(filings, sessions, tickers, max_age_days=200):
    """Only latest filing_date <= decision date, no broadcast or forward-fill leak."""
    out = pd.DataFrame(np.nan, index=sessions, columns=tickers)
    for ticker, group in filings.groupby("ticker", sort=True):
        if ticker not in out:
            continue
        g = group.copy()
        g["filing_date"] = pd.to_datetime(g.filing_date)
        # Stable report-period tie break; no use of later filing revisions.
        order = ["filing_date"] + (["report_period"] if "report_period" in g else [])
        g = g.sort_values(order, kind="stable").drop_duplicates("filing_date", keep="last")
        fd = g.filing_date.to_numpy(dtype="datetime64[ns]")
        loc = np.searchsorted(fd, sessions.to_numpy(dtype="datetime64[ns]"), side="right") - 1
        valid = loc >= 0
        safe = np.maximum(loc, 0)
        age = (sessions.to_numpy(dtype="datetime64[ns]") - fd[safe]) / np.timedelta64(1, "D")
        valid &= age <= max_age_days
        assets = g.assets.to_numpy(dtype=float, na_value=np.nan)
        profit = g.gross_profit.to_numpy(dtype=float, na_value=np.nan)
        ratio = np.divide(profit, assets, out=np.full(len(g), np.nan), where=assets > 0)
        out.loc[valid, ticker] = ratio[loc[valid]]
    return out


def rank_ic(score, returns, minimum=20):
    pair = pd.concat([score.rename("x"), returns.rename("y")], axis=1).dropna()
    if len(pair) < minimum or pair.x.nunique() < 2 or pair.y.nunique() < 2:
        return np.nan
    return float(pair.x.rank(method="average").corr(pair.y.rank(method="average")))


def mean_stats(series, sessions, horizon):
    """Calendar-aware Bartlett HAC; gaps are NOT compressed into adjacent days.

    Complete inputs reuse the protocol helper exactly. For gaps, observed
    residual score contributions remain on their original session positions;
    covariance sums use actual calendar lag, divided by observed n. Inference
    is descriptive under missingness, not a repaired confirmatory sample.
    Non-overlap counts are anchored on the original calendar, all offsets shown.
    """
    s = pd.Series(series, dtype=float).reindex(sessions)
    x = s.to_numpy()
    valid = np.isfinite(x)
    n = int(valid.sum())
    lag = max(horizon - 1, floor(4 * (n / 100) ** (2 / 9)))
    mu = float(x[valid].mean()) if n else None
    se = t = neff = None
    if valid.all() and n:
        test = newey_west(x.tolist(), horizon=horizon)
        se, t = test.se, test.t
    elif n >= max(3, lag + 2):
        u = np.where(valid, x - mu, 0)
        lrv = float(u @ u / n)
        for k in range(1, min(lag + 1, len(u))):
            lrv += 2 * (1 - k / (lag + 1)) * float(u[k:] @ u[:-k] / n)
        if lrv > 0:
            se = sqrt(lrv / n)
            t = mu / se
    if se and n > 1:
        neff = min(float(n), float(np.var(x[valid], ddof=1) / se**2))
    offsets = []
    for offset in range(horizon):
        sub = x[offset::horizon]
        sub = sub[np.isfinite(sub)]
        offsets.append(
            {"offset": offset, "n": len(sub), "mean": float(sub.mean()) if len(sub) else None}
        )
    return {
        "n": n,
        "expected_sessions": len(sessions),
        "mean": mu,
        "hac_lag": lag,
        "hac_se": se,
        "hac_t": t,
        "ci95": [mu - 1.96 * se, mu + 1.96 * se] if se else None,
        "effective_n_hac_approx": neff,
        "hit_rate": float((x[valid] > 0).mean()) if n else None,
        "nonoverlap_offset0_n": offsets[0]["n"],
        "nonoverlap_offsets": offsets,
        "gapped": not bool(valid.all()),
        "inference": "exploratory_uncorrected",
    }


def json_object(value):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def prepare_snapshots(snapshots, runs, sessions, cal):
    complete = runs[runs.status.eq("complete")].copy()
    complete["D"] = pd.to_datetime(complete.scheduled_for_date)
    s = snapshots.merge(complete, left_on="run_id", right_on="id", validate="many_to_one")
    if s.duplicated(["run_id", "ticker"]).any():
        raise ValueError("duplicate immutable snapshot key")
    # Immutable published rank is primary. Never substitute current policy_rank
    # or rerank the survivors after discovering missing forward prices.
    s["published_rank"] = pd.to_numeric(s["rank"], errors="coerce")
    for field in ("coverage", "confidence", "agreement"):
        s[field] = pd.to_numeric(s[field], errors="coerce")
    for key in ("d5", "m1", "hist"):
        s[f"consistency_{key}"] = s.consistency.map(lambda v: json_object(v).get(key, np.nan))
    for key in ("factor", "analyst"):
        # Stored dimension_scores uses UI dimension names in current payloads.
        aliases = {"factor": ("factor", "Momentum"), "analyst": ("analyst", "Analyst")}[key]
        s[f"dimension_{key}"] = s.dimension_scores.map(
            lambda v: next((json_object(v)[k] for k in aliases if k in json_object(v)), np.nan)
        )
    trading = s.D.isin(sessions)
    closes = {d: cal.session_close(d) for d in s.loc[trading, "D"].unique()}
    s["D_close"] = pd.to_datetime(s.D.map(closes), utc=True)
    asof = pd.to_datetime(s.as_of, utc=True, errors="coerce")
    created = pd.to_datetime(s.created_at, utc=True, errors="coerce")
    s["known_by_close"] = asof.le(s.D_close) & created.le(s.D_close)
    # finished_at/publication timestamps are NOT in this export: necessary-only test.
    timely = s.groupby("run_id").known_by_close.all()
    s["run_necessary_timely"] = s.run_id.map(timely)
    identity = ~(s.ticker.eq("PARA") & s.D.gt(pd.Timestamp("2025-08-06")))
    audit = {
        "complete_runs": int(complete.id.nunique()),
        "non_session_runs": int(s.loc[~trading, "run_id"].nunique()),
        "same_date_extra_runs": int(complete.D.duplicated().sum()),
        "necessary_timely_runs": int(s.loc[trading & s.run_necessary_timely, "run_id"].nunique()),
        "publication_verified": False,
        "missing_export_fields": ["finished_at", "in_universe", "source_first_seen"],
        "coverage_nonnull": int(s.coverage.notna().sum()),
        "dimension_scores_nonnull": int(s.dimension_scores.notna().sum()),
        "missing_published_rank_eligible": int((s.eligible & s.published_rank.isna()).sum()),
        "price_date_missing_fraction": float(s.price_date.isna().mean()),
        "identity_excluded_rows": int((~identity).sum()),
    }
    return s.loc[trading & identity & s.eligible].copy(), audit


def series_summary(rows, key, sessions, horizon):
    if not rows:
        return mean_stats({}, sessions, horizon)
    frame = pd.DataFrame(rows)
    # Multiple runs on the same D receive one date cluster, never extra breadth.
    return mean_stats(frame.groupby("D")[key].mean(), sessions, horizon)


def live_study(s, prices, sessions):
    output = {}
    for clean in (True, False):
        quality = "suspect_excluded" if clean else "suspect_included"
        output[quality] = {}
        for h in LIVE_H:
            fwd = forward_returns(prices, h, clean=clean)
            rows = []
            missing_counts = {a: 0 for a in ("top20", "top50", "rest", "universe")}
            eligible_counts, missing_names, attempted = [], 0, 0
            for _, g in s.groupby("run_id", sort=True):
                d = g.D.iloc[0]
                if d not in fwd.index or fwd.index.get_loc(d) + h + 1 >= len(fwd):
                    continue
                r = fwd.loc[d].reindex(g.ticker).set_axis(g.index)
                eligible_counts.append(len(g))
                attempted += len(g)
                missing_names += int(r.isna().sum())
                record = {
                    "D": d,
                    "timely": bool(g.run_necessary_timely.iloc[0]),
                    "rank_ic": rank_ic(g.published_rank, r),
                    "score_ic": rank_ic(-g.published_rank, r),
                    "composite_ic": rank_ic(g.composite_z, r),
                }
                masks = {
                    "top20": g.published_rank.le(20),
                    "top50": g.published_rank.le(50),
                    "rest": ~g.published_rank.le(50),
                    "universe": pd.Series(True, index=g.index),
                }
                all_complete = True
                for arm, mask in masks.items():
                    selected = r[mask]
                    valid = len(selected) > 0 and selected.notna().all()
                    all_complete &= valid
                    missing_counts[arm] += int(not valid)
                    record[arm] = float(selected.mean()) if selected.notna().any() else np.nan
                    record[arm + "_n"] = int(mask.sum())
                record["spy"] = float(fwd.at[d, "SPY"]) if "SPY" in fwd else np.nan
                record["common_complete"] = all_complete and np.isfinite(record["spy"])
                rows.append(record)
            result = {
                "mature_runs": len(rows),
                "mean_eligible_names": float(np.mean(eligible_counts)) if eligible_counts else None,
                "missing_forward_name_fraction": missing_names / attempted if attempted else None,
                "incomplete_runs_by_arm": missing_counts,
                "rank_ic": series_summary(rows, "rank_ic", sessions, h),
                "score_ic": series_summary(rows, "score_ic", sessions, h),
                "composite_ic": series_summary(rows, "composite_ic", sessions, h),
                "portfolios": {},
            }
            for mode in (
                "available_case_diagnostic",
                "common_complete",
                "necessary_timely_common_complete",
            ):
                chosen = [
                    r
                    for r in rows
                    if mode == "available_case_diagnostic"
                    or (r["common_complete"] and (mode == "common_complete" or r["timely"]))
                ]
                arms = {}
                for arm in ("top20", "top50", "rest", "universe", "spy"):
                    costs = {}
                    for cost in COSTS:
                        measurements = []
                        for r in chosen:
                            gross = r[arm]
                            net = round_trip_net(gross, cost)
                            unet = round_trip_net(r["universe"], cost)
                            spynet = round_trip_net(r["spy"], cost)
                            measurements.append(
                                {
                                    "D": r["D"],
                                    "net": net,
                                    "vs_ew": net - unet,
                                    "vs_spy": net - spynet,
                                }
                            )
                        costs[str(cost)] = {
                            k: series_summary(measurements, k, sessions, h)
                            for k in ("net", "vs_ew", "vs_spy")
                        }
                    arms[arm] = costs
                result["portfolios"][mode] = {"runs": len(chosen), "arms": arms}
            output[quality][str(h)] = result
    return output


def calibration_study(s, prices, sessions):
    output = {}
    for h in LIVE_H:
        fwd = forward_returns(prices, h)
        records = []
        fields = (
            "confidence",
            "agreement",
            "coverage",
            "consistency_d5",
            "consistency_m1",
            "consistency_hist",
        )
        for _, g in s.groupby("run_id", sort=True):
            d = g.D.iloc[0]
            r = fwd.loc[d].reindex(g.ticker).set_axis(g.index)
            ew = float(r.mean())
            if not np.isfinite(ew):
                continue
            excess = (1 - 10 / 10000) * (r - ew)  # identical round-trip fee conventions
            for population, mask in (
                ("eligible", pd.Series(True, index=g.index)),
                ("top50", g.published_rank.le(50)),
            ):
                for field in fields:
                    score = pd.to_numeric(g[field], errors="coerce")
                    records.append(
                        {
                            "D": d,
                            "population": population,
                            "field": field,
                            "bin": "rank_ic",
                            "value": rank_ic(score[mask], excess[mask]),
                            "names": int((mask & score.notna() & r.notna()).sum()),
                            "score_mean": float(score[mask].mean()),
                            "stock_hit": np.nan,
                        }
                    )
                    bins = pd.cut(
                        score,
                        [-0.000001, 0.5, 0.7, 1.000001],
                        labels=("low_0_0.5", "mid_0.5_0.7", "high_0.7_1"),
                        right=False,
                    )
                    for label in bins.cat.categories:
                        use = mask & bins.eq(label) & r.notna()
                        records.append(
                            {
                                "D": d,
                                "population": population,
                                "field": field,
                                "bin": label,
                                "value": float(excess[use].mean()),
                                "names": int(use.sum()),
                                "score_mean": float(score[use].mean()),
                                "stock_hit": float((excess[use] > 0).mean())
                                if use.any()
                                else np.nan,
                            }
                        )
        frame = pd.DataFrame(records)
        summary = []
        for keys, group in frame.groupby(["population", "field", "bin"], sort=True):
            summary.append(
                {
                    "population": keys[0],
                    "field": keys[1],
                    "bin": keys[2],
                    "stats": mean_stats(group.groupby("D").value.mean(), sessions, h),
                    "stock_observations_not_independent": int(group.names.sum()),
                    "mean_displayed_score": float(group.score_mean.mean()),
                    "mean_date_stock_hit": float(group.stock_hit.mean()),
                }
            )
        for keys, group in frame.groupby(["population", "field"], sort=True):
            wide = group.pivot_table(index="D", columns="bin", values="value")
            if {"low_0_0.5", "high_0.7_1"}.issubset(wide.columns):
                summary.append(
                    {
                        "population": keys[0],
                        "field": keys[1],
                        "bin": "paired_high_minus_low",
                        "stats": mean_stats(wide["high_0.7_1"] - wide["low_0_0.5"], sessions, h),
                    }
                )
        output[str(h)] = summary
    return output


def signal_study(fast, prices, sessions, cal):
    f = fast.copy()
    f["D"] = pd.to_datetime(f.date)
    f = f[f.D.isin(sessions)]
    # Signal-family diagnostics anchor on its own first observed date, not on
    # February price warmup or the earlier snapshot experiment.
    sessions = sessions[sessions >= f.D.min()]
    closes = {d: cal.session_close(d) for d in f.D.unique()}
    f["timely"] = pd.to_datetime(f.fetched_at, utc=True).le(
        pd.to_datetime(f.D.map(closes), utc=True)
    )
    f = f[~(f.ticker.eq("PARA") & f.D.gt(pd.Timestamp("2025-08-06")))]
    results = []
    for h in LIVE_H:
        fwd = forward_returns(prices, h)
        for meta in SIGNAL_REGISTRY:
            sub = f[f.signal.eq(meta.name)]
            for timing in ("all_diagnostic", "fetched_by_D_close"):
                use = sub if timing == "all_diagnostic" else sub[sub.timely]
                records = []
                for d, group in use.groupby("D", sort=True):
                    score = group.set_index("ticker").z
                    r = fwd.loc[d].reindex(score.index)
                    records.append({"D": d, "ic": rank_ic(score, r)})
                ic = pd.DataFrame(records, columns=["D", "ic"]).set_index("D").ic
                monthly = {
                    str(month): {"n": int(g.notna().sum()), "ic": float(g.mean())}
                    for month, g in ic.groupby(ic.index.strftime("%Y-%m"))
                }
                results.append(
                    {
                        "signal": meta.name,
                        "h": h,
                        "timing": timing,
                        "static_weight": meta.default_weight,
                        "cap": meta.fusion_cap,
                        "native_horizon": meta.horizon_days,
                        "mean_effective_w": float(sub.w.mean()),
                        "nonzero_w_fraction": float(sub.w.gt(0).mean()),
                        "ic": mean_stats(ic, sessions, h),
                        "months": monthly,
                        "positive_months": sum(g["ic"] > 0 for g in monthly.values()),
                        "negative_months": sum(g["ic"] < 0 for g in monthly.values()),
                    }
                )
    return results


def selection_sets(s):
    """Fixed pre-result rules, using only immutable snapshot fields.

    No same-date fast-signal merge (no run_id alignment); missing agreement
    inputs make that rule unavailable, not a successful empty portfolio.
    Buy-band: retain prior published names within rank80; admit rank<=40 to
    vacant slots, at most50; missing run does not create a fabricated decision.
    """
    output = []
    held = set()
    for _, g in s.sort_values(["D", "run_id", "published_rank", "ticker"]).groupby(
        "run_id", sort=False
    ):
        rank = g.set_index("ticker").published_rank
        held &= set(rank[rank.le(80)].index)
        for ticker in rank[rank.le(40)].index:
            if len(held) < 50:
                held.add(ticker)
        for rule in RULES:
            if rule == "top50":
                names = set(g.loc[g.published_rank.le(50), "ticker"])
            elif rule == "buy40_hold80":
                names = set(held)
            elif rule == "coverage_ge_0.8":
                names = (
                    set(g.loc[g.published_rank.le(50) & g.coverage.ge(0.8), "ticker"])
                    if g.coverage.notna().any()
                    else None
                )
            else:
                known = g.dimension_factor.notna() & g.dimension_analyst.notna()
                # Complete Top50 input required, not subset selection on missing fields.
                names = (
                    set(
                        g.loc[
                            g.published_rank.le(50)
                            & g.dimension_factor.gt(0)
                            & g.dimension_analyst.gt(0),
                            "ticker",
                        ]
                    )
                    if known[g.published_rank.le(50)].all() and g.published_rank.le(50).any()
                    else None
                )
            output.append(
                {"D": g.D.iloc[0], "run_id": g.run_id.iloc[0], "rule": rule, "names": names}
            )
    return output


def selection_study(s, prices, sessions):
    sets = selection_sets(s)
    results = []
    churn_rows = []
    for rule in RULES:
        previous = None
        for item in [v for v in sets if v["rule"] == rule]:
            if item["names"] is None:
                continue
            weights = pd.Series(1 / 50, index=sorted(item["names"]), dtype=float)
            if previous is not None:
                churn_rows.append(
                    {
                        "D": item["D"],
                        "rule": rule,
                        "churn": float(weights.subtract(previous, fill_value=0).abs().sum()),
                    }
                )
            previous = weights
    churn_frame = pd.DataFrame(churn_rows, columns=["D", "rule", "churn"])
    churn_wide = churn_frame.pivot_table(index="D", columns="rule", values="churn")
    for h in LIVE_H:
        fwd = forward_returns(prices, h)
        for rule in RULES:
            records = []
            unavailable, incomplete = 0, 0
            churn, previous = [], None
            for item in [v for v in sets if v["rule"] == rule]:
                d, names = item["D"], item["names"]
                if names is None:
                    unavailable += 1
                    continue
                w = pd.Series(1 / 50, index=sorted(names), dtype=float)
                if previous is not None:
                    churn.append(float(w.subtract(previous, fill_value=0).abs().sum()))
                previous = w
                row = fwd.loc[d].reindex(sorted(names))
                if row.isna().any() or fwd.index.get_loc(d) + h + 1 >= len(fwd):
                    incomplete += 1
                    continue
                gross = float(row.sum() / 50)  # unfilled slots stay cash; no survivor rerank
                exposure = len(names) / 50
                base = next(
                    v["names"]
                    for v in sets
                    if v["run_id"] == item["run_id"] and v["rule"] == "top50"
                )
                base_r = fwd.loc[d].reindex(sorted(base))
                for cost in COSTS:
                    net = gross - cost / 10000 * (2 * exposure + gross)
                    bnet = (
                        float(base_r.sum() / 50)
                        - cost / 10000 * (2 * len(base) / 50 + float(base_r.sum() / 50))
                        if base_r.notna().all()
                        else np.nan
                    )
                    records.append(
                        {
                            "D": d,
                            "cost": cost,
                            "net": net,
                            "delta_top50": net - bnet,
                            "exposure": exposure,
                        }
                    )
            frame = pd.DataFrame(records, columns=["D", "cost", "net", "delta_top50", "exposure"])
            results.append(
                {
                    "rule": rule,
                    "h": h,
                    "unavailable_runs": unavailable,
                    "incomplete_or_immature_runs": incomplete,
                    "mean_target_gross_churn_per_observed_run": float(np.mean(churn))
                    if churn
                    else None,
                    "churn_note": "target-list churn, excludes drift, spans gaps; not executable daily turnover",
                    "mean_exposure": float(frame.exposure.mean()),
                    "churn_delta_top50": mean_stats(
                        churn_wide[rule] - churn_wide["top50"], sessions, 1
                    )
                    if rule in churn_wide
                    else mean_stats({}, sessions, 1),
                    "costs": {
                        str(c): {
                            k: mean_stats(
                                frame[frame.cost.eq(c)].groupby("D")[k].mean(), sessions, h
                            )
                            for k in ("net", "delta_top50")
                        }
                        for c in COSTS
                    },
                }
            )
    return results


def cohort_rebalance(scores, fwd, members, days, horizon, cost, *, offset=0):
    """Exploratory fractional h-session portfolios with drift-aware turnover.

    Predetermined decision grid; no gap compression. A missing selected label
    invalidates that cohort AND its next rebalance turnover. Subsequent clean
    cohorts restart from cash and pay a fresh entry fee. Not an integer-share,
    20%-budget replay of the frozen protocol. Includes uniform terminal exit.
    """
    records = []
    previous = {"top": None, "ew": None}

    def end_segment(arm):
        if records and previous[arm] is not None:
            last = records[-1]
            last[arm] -= cost / 10000 * last[arm + "_exit_notional"]
            last[arm + "_turnover"] += last[arm + "_exit_notional"]
        previous[arm] = None

    for d in days[offset::horizon]:
        sc = scores.loc[d].where(members.loc[d]).dropna().sort_index()
        ordered = sc.sort_values(ascending=False, kind="stable")
        groups = {"top": list(ordered.index[: int(np.ceil(len(sc) / 5))]), "ew": list(sc.index)}
        record = {"D": d}
        for arm, names in groups.items():
            if not names:
                end_segment(arm)
                previous[arm] = None
                record[arm] = np.nan
                continue
            target = pd.Series(min(1 / len(names), 0.02), index=names)
            rr = fwd.loc[d].reindex(names)
            if rr.isna().any():
                end_segment(arm)
                previous[arm] = None
                record[arm] = np.nan
                continue
            old = previous[arm]
            delta = target.subtract(
                old if old is not None else pd.Series(dtype=float), fill_value=0
            )
            buy = float(delta.clip(lower=0).sum())
            sell = float(-delta.clip(upper=0).sum())
            gross = float((target * rr).sum())
            net = gross - cost / 10000 * (buy + sell)
            record[arm] = net
            record[arm + "_turnover"] = buy + sell
            record[arm + "_names"] = len(names)
            # Net wealth denominator includes rebalance costs; reserve cash
            # cost approximation means this is a return diagnostic, not orders.
            previous[arm] = target * (1 + rr) / (1 + gross)
            record[arm + "_exit_notional"] = float((target * (1 + rr)).sum())
        records.append(record)
    if records:
        for arm in previous:
            end_segment(arm)
    grid = days[offset::horizon]
    frame = pd.DataFrame(
        records, columns=["D", "top", "ew", "top_turnover", "ew_turnover", "top_names", "ew_names"]
    ).set_index("D")
    diff = frame.top - frame.ew
    return {
        "excess": mean_stats(diff, grid, 1),
        "top_net": mean_stats(frame.top, grid, 1),
        "expected_cohorts": len(grid),
        "complete_paired_cohorts": int(diff.notna().sum()),
        "mean_gross_turnover": float(frame.top_turnover.mean()),
        "mean_ew_turnover": float(frame.ew_turnover.mean()),
        "mean_top_names": float(frame.top_names.mean()),
        "offset": offset,
    }


def factor_study(prices, members, factors, sessions):
    windows = {
        "train": PROTOCOL.train,
        "validation1": PROTOCOL.validation[0],
        "validation2": PROTOCOL.validation[1],
        "historical_test_not_unseen": PROTOCOL.historical_test,
    }
    results, purge = [], []
    dates = tuple(d.date() for d in sessions)
    for h in FACTOR_H:
        for i, evaluation in enumerate(PROTOCOL.validation):
            prefix = DateRange(
                PROTOCOL.train.start, PROTOCOL.train.end if i == 0 else PROTOCOL.validation[0].end
            )
            kept = purged_training_dates(
                dates, prefix, evaluation, horizon=h, embargo=max(21, h + 1)
            )
            purge.append(
                {
                    "h": h,
                    "validation": i + 1,
                    "training_decisions_retained": len(kept),
                    "last_training_D": str(kept[-1]) if kept else None,
                    "embargo": max(21, h + 1),
                }
            )
        for name, window in windows.items():
            block = sessions[
                (sessions >= pd.Timestamp(window.start)) & (sessions <= pd.Timestamp(window.end))
            ]
            mature = block[: max(0, len(block) - h - 1)]
            fwd = forward_returns(prices, h, block_end=window.end)
            for factor, scores in factors.items():
                ic = {d: rank_ic(scores.loc[d].where(members.loc[d]), fwd.loc[d]) for d in mature}
                diagnostic = []
                counts = []
                for d in mature:
                    sc = scores.loc[d].where(members.loc[d]).dropna().sort_index()
                    names = sc.sort_values(ascending=False, kind="stable").index[
                        : int(np.ceil(len(sc) / 5))
                    ]
                    top = fwd.loc[d].reindex(names)
                    ew = fwd.loc[d].reindex(sc.index)
                    full = fwd.loc[d].where(members.loc[d])
                    counts.append(
                        {
                            "eligible": int(members.loc[d].sum()),
                            "scorable": len(sc),
                            "selected": len(names),
                            "selected_valid": int(top.notna().sum()),
                            "ew_valid": int(ew.notna().sum()),
                        }
                    )
                    for cost in COSTS:
                        diagnostic.append(
                            {
                                "D": d,
                                "cost": cost,
                                "vs_scorable_ew": round_trip_net(top.mean(), cost)
                                - round_trip_net(ew.mean(), cost),
                                "vs_full_eligible_ew": round_trip_net(top.mean(), cost)
                                - round_trip_net(full.mean(), cost),
                            }
                        )
                diag = pd.DataFrame(
                    diagnostic, columns=["D", "cost", "vs_scorable_ew", "vs_full_eligible_ew"]
                )
                sensitivity = {}
                for cost in COSTS:
                    offsets = [
                        cohort_rebalance(scores, fwd, members, mature, h, cost, offset=o)
                        for o in range(h)
                    ]
                    sensitivity[str(cost)] = {"offset0": offsets[0], "all_offsets": offsets}
                results.append(
                    {
                        "factor": factor,
                        "h": h,
                        "window": name,
                        "unseen": False,
                        "expected_block_sessions": len(block),
                        "mature_decisions": len(mature),
                        "mean_cross_section_counts": pd.DataFrame(counts).mean().to_dict(),
                        "available_case_roundtrip_diagnostic": {
                            str(c): {
                                k: mean_stats(
                                    diag[diag.cost.eq(c)].groupby("D")[k].mean(), block, h
                                )
                                for k in ("vs_scorable_ew", "vs_full_eligible_ew")
                            }
                            for c in COSTS
                        },
                        "ic": mean_stats(ic, block, h),
                        "costs": sensitivity,
                    }
                )
    return {"results": results, "purge_audit": purge}


def load_inputs(data_dir):
    names = ("daily_prices", "rating_snapshot", "research_run", "fast_signal_z")
    paths = {name: data_dir / f"{name}.parquet" for name in names}
    data = {name: pd.read_parquet(path) for name, path in paths.items()}
    hashes = {name: sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    return data, hashes


def load_bundle(panel_path, pit_path):
    # Same uncached, temporary path-override loader pattern as baselines.py.
    from alpha_agent.factor_engine import factor_backtest as fb
    from alpha_agent.data import membership

    with (
        patch.object(fb, "PARQUET_PATH", panel_path),
        patch.object(fb, "PIT_FUNDAMENTALS_PATH", pit_path),
    ):
        panel = fb._load_panel.__wrapped__()
    if panel.is_member is None:
        raise ValueError("PIT membership missing; refusing all-member fallback")
    sessions, _ = xnys_sessions(str(panel.dates[0])[:10], str(panel.dates[-1])[:10])
    actual = pd.DatetimeIndex(pd.to_datetime(panel.dates))
    if not sessions.equals(actual):
        raise ValueError("bundled calendar incomplete")
    prices = pd.DataFrame(panel.close, index=sessions, columns=panel.tickers)
    members = pd.DataFrame(panel.is_member, index=sessions, columns=panel.tickers)
    members &= identity_mask(sessions, panel.tickers)
    # Exact preset DSL semantics, including rank tie behavior and membership
    # mask AFTER the expression. Do not quietly replace this with pandas rank.
    from alpha_agent.scan.vectorized import evaluate

    trailing = prices.pct_change(fill_method=None)
    preset = evaluate(
        "subtract(rank(ts_mean(returns, 12)), rank(ts_std(returns, 60)))",
        {"returns": trailing.to_numpy()},
    )
    quality = pit_quality(pd.read_parquet(pit_path), sessions, panel.tickers)
    factors = {
        FACTORS[0]: pd.DataFrame(preset, index=sessions, columns=panel.tickers),
        FACTORS[1]: prices.shift(21) / prices.shift(252) - 1,
        FACTORS[2]: -trailing.rolling(60, min_periods=60).std(ddof=0),
        FACTORS[3]: quality,
    }
    hashes = {
        "bundle": sha256(panel_path.read_bytes()).hexdigest(),
        "pit": sha256(pit_path.read_bytes()).hexdigest(),
        "membership": sha256(membership._DEFAULT_CSV.read_bytes()).hexdigest(),
    }
    manifest = ROOT / "alpha_agent/data/research_dataset.json"
    updates = ROOT / "alpha_agent/data/membership_updates.json"
    hashes["manifest"] = sha256(manifest.read_bytes()).hexdigest()
    hashes["membership_updates_not_applied_by_loader"] = sha256(updates.read_bytes()).hexdigest()
    return prices, members, factors, sessions, hashes


def trial_log():
    """Full pre-result search grid; never increment only for the winner."""
    log = []

    def add(family, variant, horizon):
        log.append(
            {
                "id": len(log) + 1,
                "family": family,
                "variant": variant,
                "h": horizon,
                "status": "attempted_even_if_unavailable",
            }
        )

    for h in LIVE_H:
        for arm in ("top20", "top50", "rest"):
            add("Q1", arm, h)
        for m in SIGNAL_REGISTRY:
            add("Q2_signal", m.name, h)
        for population in ("eligible", "top50"):
            for field in (
                "confidence",
                "agreement",
                "coverage",
                "consistency_d5",
                "consistency_m1",
                "consistency_hist",
            ):
                add("Q2_calibration", f"{population}:{field}:3_fixed_bins_and_rank_ic", h)
        for rule in RULES:
            add("Q4", rule, h)
    for factor in FACTORS:
        for h in FACTOR_H:
            add("Q3", factor, h)
    return log


def number(value, scale=1, digits=3):
    return "未知" if value is None or not np.isfinite(value) else f"{value * scale:.{digits}f}"


def markdown_summary(result):
    lines = [
        "# Top50 离线研究汇总",
        "",
        "仅探索性关联；不授权改动现有系统。收益为每个持有期的百分比，不是日收益或年化。",
        "",
        f"试验登记：{len(result['trial_log'])} 个主规格；全部费用、质量、时间、窗口、offset 敏感性保留在 JSON。",
        "",
        "## Q1 已发布排名：available-case 诊断",
        "",
        "|h|臂|成熟日期|净收益%|超额EW%|超额SPY%|EW超额HAC t|95% CI（%）|offset0块数|",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for h in LIVE_H:
        q = result["q1"]["suspect_excluded"][str(h)]
        for arm in ("top20", "top50", "rest"):
            a = q["portfolios"]["available_case_diagnostic"]["arms"][arm]["10"]
            s = a["vs_ew"]
            ci = s["ci95"]
            lines.append(
                f"|{h}|{arm}|{s['n']}|{number(a['net']['mean'], 100)}|{number(s['mean'], 100)}|{number(a['vs_spy']['mean'], 100)}|{number(s['hac_t'])}|{number(ci[0], 100) if ci else '未知'}…{number(ci[1], 100) if ci else '未知'}|{s['nonoverlap_offset0_n']}|"
            )
    lines += [
        "",
        "严格样本另列；上表会在当时名单不变的前提下，对未来可用标签取均值，存在缺失选择偏差。",
        "",
        "|h|全臂完整日期|Top50-EW%|必要时间条件+全臂完整日期|Top50-EW%|",
        "|---|---|---|---|---|",
    ]
    for h in LIVE_H:
        q = result["q1"]["suspect_excluded"][str(h)]["portfolios"]
        a = q["common_complete"]["arms"]["top50"]["10"]["vs_ew"]
        b = q["necessary_timely_common_complete"]["arms"]["top50"]["10"]["vs_ew"]
        lines.append(f"|{h}|{a['n']}|{number(a['mean'], 100)}|{b['n']}|{number(b['mean'], 100)}|")
    lines += [
        "",
        "## Q2 单信号（fetched_by_D_close，5日）",
        "",
        "|信号|先验权重|平均有效权重|IC|HAC t|日期|正/负月份|",
        "|---|---|---|---|---|---|---|",
    ]
    for s in result["q2_signals"]:
        if s["h"] == 5 and s["timing"] == "fetched_by_D_close":
            lines.append(
                f"|{s['signal']}|{number(s['static_weight'])}|{number(s['mean_effective_w'])}|{number(s['ic']['mean'])}|{number(s['ic']['hac_t'])}|{s['ic']['n']}|{s['positive_months']}/{s['negative_months']}|"
            )
    lines += [
        "",
        "Top50 置信字段与5日超额的秩相关：",
        "",
        "|字段|IC|95% CI|日期|",
        "|---|---|---|---|",
    ]
    for row in result["q2_calibration"]["5"]:
        if row["population"] == "top50" and row["bin"] == "rank_ic":
            s = row["stats"]
            ci = s["ci95"]
            lines.append(
                f"|{row['field']}|{number(s['mean'])}|{number(ci[0]) if ci else '未知'}…{number(ci[1]) if ci else '未知'}|{s['n']}|"
            )
    lines += [
        "",
        "## Q3 面板家族与期限：固定主offset0、10bps",
        "",
        "|窗口|因子|h|IC|净超额EW%/期|95% CI（%）|非重叠块数|双边换手/期|",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in result["q3"]["results"]:
        a = s["costs"]["10"]["offset0"]
        ci = a["excess"]["ci95"]
        lines.append(
            f"|{s['window']}|{s['factor']}|{s['h']}|{number(s['ic']['mean'])}|{number(a['excess']['mean'], 100)}|{number(ci[0], 100) if ci else '未知'}…{number(ci[1], 100) if ci else '未知'}|{a['excess']['n']}|{number(a['mean_gross_turnover'], 100)}%|"
        )
    lines += [
        "",
        "## Q4 固定规则（5日、10bps、完整入选标签）",
        "",
        "|规则|成熟日期|净收益%|相对Top50增量%|平均仓位|目标名单双边变化|缺字段运行|",
        "|---|---|---|---|---|---|---|",
    ]
    for q in result["q4"]:
        if q["h"] == 5:
            a = q["costs"]["10"]
            lines.append(
                f"|{q['rule']}|{a['net']['n']}|{number(a['net']['mean'], 100)}|{number(a['delta_top50']['mean'], 100)}|{number(q['mean_exposure'], 100)}%|{number(q['mean_target_gross_churn_per_observed_run'], 100)}%|{q['unavailable_runs']}|"
            )
    return "\n".join(lines) + "\n"


def json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return float(obj) if np.isfinite(obj) else None
    return obj


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/tmp/alpha-research/data"))
    parser.add_argument(
        "--panel", type=Path, default=ROOT / "alpha_agent/data/factor_universe_sp500_v3.parquet"
    )
    parser.add_argument(
        "--pit", type=Path, default=ROOT / "alpha_agent/data/fundamentals_pit_sp500_v3.parquet"
    )
    parser.add_argument("--out-dir", type=Path, default=Path("/tmp/alpha-research/out/top50"))
    args = parser.parse_args()
    if args.out_dir.resolve().is_relative_to(ROOT):
        parser.error("private output must be outside the public worktree")
    started = time.monotonic()
    data, hashes = load_inputs(args.data_dir)
    daily = data["daily_prices"].copy()
    daily["date"] = pd.to_datetime(daily.date)
    sessions, cal = xnys_sessions(daily.date.min().date(), daily.date.max().date())
    prices = daily.pivot(index="date", columns="ticker", values="close").reindex(sessions)
    snaps, audit = prepare_snapshots(data["rating_snapshot"], data["research_run"], sessions, cal)
    evaluation_sessions = sessions[sessions >= snaps.D.min()]
    audit["evaluation_start"] = str(evaluation_sessions[0].date())
    audit["evaluation_end"] = str(evaluation_sessions[-1].date())
    audit["expected_evaluation_sessions"] = len(evaluation_sessions)
    jumps = prices.pct_change(fill_method=None).abs().gt(0.35)
    audit["suspect_move_cells"] = int(jumps.sum().sum())
    audit["suspect_tickers_count"] = int(jumps.any().sum())
    result = {
        "study_version": "top50-exploratory-v0.1-20261112",
        "protocol": PROTOCOL.to_dict(),
        "protocol_fingerprint": PROTOCOL.fingerprint,
        "audit": audit,
        "input_hashes": hashes,
        "trial_log": trial_log(),
        "dsr": {
            "status": "unverified",
            "reason": "prior global search count unknown; no winner promotion",
        },
        "interpretation": {
            "status": "evidence_insufficient_for_live_changes",
            "ci": "uncorrected descriptive normal HAC intervals, NOT confirmatory or profit probabilities",
            "q1_cost": "equal-weight independent cohorts, both arms pay entry+exit; not a continuous NAV",
            "q3_cost": "fractional h-session target rebalance, no 20% trade budget; gap segments liquidated at prior known endpoint; not executable order replay",
            "missing": "available-case diagnostics never replace complete-cohort evidence; all selected missing-label denominators retained",
            "trial_count": "111 primary specifications, sensitivities and all unavailable cells retained; not 111 independent hypotheses; prior global count unknown",
        },
    }
    print("Q1/Q2/Q4: local snapshot diagnostics", flush=True)
    result["q1"] = live_study(snaps, prices, evaluation_sessions)
    result["q2_calibration"] = calibration_study(snaps, prices, evaluation_sessions)
    result["q2_signals"] = signal_study(data["fast_signal_z"], prices, evaluation_sessions, cal)
    result["q4"] = selection_study(snaps, prices, evaluation_sessions)
    result["q4_necessary_timely"] = selection_study(
        snaps[snaps.run_necessary_timely], prices, evaluation_sessions
    )
    print("Q3: bundled PIT panel", flush=True)
    bp, member, factors, bs, bh = load_bundle(args.panel, args.pit)
    result["input_hashes"].update(bh)
    result["q3"] = factor_study(bp, member, factors, bs)
    result["q3"]["membership_note"] = (
        "loader CSV only; membership_updates.json not applied; no survivorship-free claim"
    )
    result["q3"]["quality_note"] = (
        "PIT publication-date <=D; 200-day expiry; filing intraday release/revision vintage unknown"
    )
    elapsed_seconds = round(time.monotonic() - started, 3)
    result = json_safe(result)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    (args.out_dir / "summary.md").write_text(markdown_summary(result))
    print(
        json.dumps(
            {
                "outputs": [str(args.out_dir / "summary.json"), str(args.out_dir / "summary.md")],
                "elapsed_seconds": elapsed_seconds,
                "trial_count": len(result["trial_log"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
