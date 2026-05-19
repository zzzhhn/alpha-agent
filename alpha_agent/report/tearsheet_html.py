"""Slim self-contained HTML tearsheet generator (B6, 2026-05-19).

Phase 3 backlog item B6. Source: synthesizer T11 — QuantStats-style
single-file portable tearsheet. The QuantStats library itself was the
synthesizer's framing but is matplotlib-heavy (40MB+ in a Vercel
lambda) and would trip `feedback_vercel_lambda_dependency_size.md`.
This module ships the same shape (one .html file the user downloads
and pings to colleagues) using only jinja2 + Chart.js via CDN — zero
new Python deps, ~3KB rendered baseline plus the embedded JSON data.

Design notes:
- jinja2 is already in pyproject; matplotlib intentionally not imported.
- Chart.js loaded from cdn.jsdelivr.net (same source the existing
  static_report.html scaffold uses) so the downloaded file works
  offline only if the user has Chart.js cached / inlined. For v1 the
  CDN dep is acceptable; future variant can inline the ~70KB minified
  bundle when fully-offline is required.
- The template renders the same metrics the AttributionTable + B1
  joint panel already surface, so a colleague reviewing the .html
  sees identical numbers to the live app.
- Pandas / numpy are unused here — caller hands in a plain dict.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from jinja2 import Template


_TEMPLATE = Template(
    """<!DOCTYPE html>
<html lang="{{ locale }}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>alpha-agent · {{ factor_name }} tearsheet</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --bg: #0f172a; --card: #1e293b; --border: #334155;
      --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8;
      --green: #4ade80; --red: #f87171; --yellow: #fbbf24;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
           background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem 1.5rem; }
    .container { max-width: 1040px; margin: 0 auto; }
    header { border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; margin-bottom: 2rem; }
    h1 { font-size: 1.5rem; font-weight: 700; }
    h2 { font-size: 1.1rem; font-weight: 600; margin: 2rem 0 0.75rem; color: var(--accent); }
    .meta { color: var(--muted); font-size: 0.85rem; margin-top: 0.5rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
             gap: 0.75rem; margin-bottom: 1.5rem; }
    .cell { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
            padding: 0.75rem 1rem; }
    .cell .label { color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; }
    .cell .value { font-size: 1.15rem; font-weight: 600; margin-top: 0.25rem; font-variant-numeric: tabular-nums; }
    .cell .value.pos { color: var(--green); }
    .cell .value.neg { color: var(--red); }
    .chart-wrap { background: var(--card); border: 1px solid var(--border);
                  border-radius: 6px; padding: 1rem; margin-bottom: 1.5rem; height: 300px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th, td { padding: 0.4rem 0.6rem; text-align: right; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: 500; text-align: left; }
    td:first-child, th:first-child { text-align: left; }
    .footer { color: var(--muted); font-size: 0.75rem; margin-top: 3rem;
              padding-top: 1rem; border-top: 1px solid var(--border); }
    .btn { display: inline-block; background: var(--accent); color: var(--bg);
           padding: 0.4rem 0.85rem; border-radius: 4px; border: none; cursor: pointer;
           font-weight: 600; font-size: 0.8rem; }
    .btn:hover { opacity: 0.85; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>{{ factor_name }}</h1>
      <div class="meta">
        generated {{ generated_at }} ·
        universe {{ universe }} · benchmark {{ benchmark }} ·
        direction {{ direction }} · neutralize {{ neutralize }} ·
        survivorship {{ "✓ corrected" if survivorship_corrected else "× legacy" }}
      </div>
    </header>

    <h2>HEADLINE METRICS</h2>
    <div class="grid">
      {% for cell in headline_cells %}
        <div class="cell">
          <div class="label">{{ cell.label }}</div>
          <div class="value {{ cell.tone }}">{{ cell.value }}</div>
        </div>
      {% endfor %}
    </div>

    <h2>EQUITY CURVE</h2>
    <div class="chart-wrap"><canvas id="equity-chart"></canvas></div>

    <h2>DRAWDOWN</h2>
    <div class="chart-wrap"><canvas id="dd-chart"></canvas></div>

    {% if monthly_returns %}
    <h2>MONTHLY RETURNS</h2>
    <table>
      <thead>
        <tr><th>Year</th>{% for m in 'JFMAMJJASOND' %}<th>{{ m }}</th>{% endfor %}<th>YTD</th></tr>
      </thead>
      <tbody>
        {% for row in monthly_table %}
          <tr>
            <td>{{ row.year }}</td>
            {% for v in row.months %}
              <td style="color: {% if v is none %}var(--muted){% elif v > 0 %}var(--green){% else %}var(--red){% endif %};">
                {% if v is none %}—{% else %}{{ "%+.1f%%"|format(v * 100) }}{% endif %}
              </td>
            {% endfor %}
            <td style="font-weight: 600; color: {% if row.ytd >= 0 %}var(--green){% else %}var(--red){% endif %};">
              {{ "%+.1f%%"|format(row.ytd * 100) }}
            </td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
    {% endif %}

    <h2>RAW METRICS</h2>
    <table>
      <tbody>
        {% for k, v in raw_metrics.items() %}
          <tr><td>{{ k }}</td><td>{{ v }}</td></tr>
        {% endfor %}
      </tbody>
    </table>

    <div class="footer">
      <button class="btn" onclick="downloadJson()">Download raw JSON</button>
      <p style="margin-top: 0.5rem;">
        Generated by alpha-agent · B6 tearsheet · self-contained, no server pings.
      </p>
    </div>
  </div>

  <script>
    const equityData = {{ equity_json|safe }};
    const ddData = {{ dd_json|safe }};
    const rawJson = {{ raw_json|safe }};
    const chartFontColor = '#94a3b8';

    new Chart(document.getElementById('equity-chart'), {
      type: 'line',
      data: {
        labels: equityData.map(p => p.date),
        datasets: [
          { label: 'Factor', data: equityData.map(p => p.value), borderColor: '#38bdf8', borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
          { label: 'Benchmark', data: equityData.map(p => p.bench), borderColor: '#94a3b8', borderWidth: 1, borderDash: [4, 4], pointRadius: 0 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: chartFontColor } } },
        scales: {
          x: { ticks: { color: chartFontColor, maxTicksLimit: 8 }, grid: { color: '#334155' } },
          y: { ticks: { color: chartFontColor }, grid: { color: '#334155' } }
        }
      }
    });

    new Chart(document.getElementById('dd-chart'), {
      type: 'line',
      data: {
        labels: ddData.map(p => p.date),
        datasets: [{ label: 'Drawdown', data: ddData.map(p => p.dd * 100), borderColor: '#f87171', backgroundColor: 'rgba(248,113,113,0.2)', fill: true, pointRadius: 0, tension: 0.1 }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: chartFontColor } } },
        scales: {
          x: { ticks: { color: chartFontColor, maxTicksLimit: 8 }, grid: { color: '#334155' } },
          y: { ticks: { color: chartFontColor, callback: v => v + '%' }, grid: { color: '#334155' } }
        }
      }
    });

    function downloadJson() {
      const blob = new Blob([JSON.stringify(rawJson, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = '{{ factor_name }}.json';
      a.click();
      URL.revokeObjectURL(a.href);
    }
  </script>
</body>
</html>
"""
)


def _equity_with_drawdown(equity_curve: list[dict], benchmark_curve: list[dict] | None) -> tuple[list[dict], list[dict]]:
    """Zip equity + benchmark into a single chart-friendly list + emit a
    drawdown series. Both side-stream so the template renders 1 .map per
    chart. Drawdown = peak-to-trough, normalised to fraction in [-1, 0]."""
    bench_lookup = {b["date"]: b["value"] for b in (benchmark_curve or [])}
    equity = []
    peak = -float("inf")
    dd = []
    for p in equity_curve:
        v = float(p.get("value", 0))
        equity.append({"date": p["date"], "value": v, "bench": bench_lookup.get(p["date"])})
        if v > peak:
            peak = v
        dd.append({"date": p["date"], "dd": (v - peak) / peak if peak else 0.0})
    return equity, dd


def _monthly_table(monthly_returns: list[dict]) -> list[dict]:
    """Pivot the flat monthly_returns list into a per-year row + YTD cell."""
    out: dict[int, list[float | None]] = {}
    for r in monthly_returns:
        year = int(r["year"])
        month = int(r["month"]) - 1
        out.setdefault(year, [None] * 12)
        out[year][month] = float(r["return"])
    rows = []
    for year in sorted(out):
        months = out[year]
        # YTD = cumulative product of monthly returns present
        ytd = 1.0
        for m in months:
            if m is not None:
                ytd *= 1 + m
        ytd -= 1
        rows.append({"year": year, "months": months, "ytd": ytd})
    return rows


def _format_pct(x: float) -> str:
    return f"{x * 100:+.2f}%" if x else "0.00%"


def render_tearsheet(result: dict[str, Any], factor_name: str = "factor", locale: str = "en") -> str:
    """Generate a single-file self-contained HTML tearsheet for a
    FactorBacktestResponse-shaped dict. No external Python deps beyond
    jinja2 (already in deps). Chart.js loaded via CDN at render-time."""

    test = result.get("test_metrics", {}) or {}
    train = result.get("train_metrics", {}) or {}

    headline_cells = []
    for label, raw, fmt, tone_thresh in [
        ("Sharpe (OOS)", test.get("sharpe"), "{:+.2f}", 0.0),
        ("Alpha (ann.)", result.get("alpha_annualized"), "{:+.2%}", 0.0),
        ("Beta (mkt)", result.get("beta_market"), "{:+.2f}", None),
        ("R²", result.get("r_squared"), "{:.3f}", None),
        ("Rank IC", test.get("rank_ic_mean"), "{:+.3f}", 0.0),
        ("ICIR", test.get("rank_icir"), "{:+.2f}", 0.5),
        ("Max DD", test.get("max_drawdown"), "{:+.1%}", None),
        ("Turnover", test.get("turnover"), "{:.2f}", None),
    ]:
        if raw is None:
            headline_cells.append({"label": label, "value": "—", "tone": ""})
            continue
        try:
            value = fmt.format(float(raw))
            tone = ""
            if tone_thresh is not None:
                tone = "pos" if float(raw) >= tone_thresh else "neg"
            headline_cells.append({"label": label, "value": value, "tone": tone})
        except (TypeError, ValueError):
            headline_cells.append({"label": label, "value": str(raw), "tone": ""})

    equity, dd = _equity_with_drawdown(
        result.get("equity_curve", []) or [],
        result.get("benchmark_curve", []) or [],
    )

    monthly = result.get("monthly_returns") or []
    monthly_table = _monthly_table(monthly) if monthly else []

    raw_metrics = {
        "Train Sharpe": _format_pct(train.get("sharpe", 0)),
        "Test Sharpe": _format_pct(test.get("sharpe", 0)),
        "OOS Decay": _format_pct(result.get("oos_decay", 0)),
        "Overfit Flag": str(result.get("overfit_flag", False)),
        "Alpha t-stat": f"{float(result.get('alpha_t_stat') or 0):+.2f}",
        "Alpha p-value": f"{float(result.get('alpha_pvalue') or 1):.4f}",
        "Membership as-of": result.get("membership_as_of") or "—",
        "Neutralize": result.get("neutralize") or "none",
    }

    return _TEMPLATE.render(
        factor_name=factor_name,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        locale=locale,
        universe="SP500",
        benchmark=result.get("benchmark_ticker", "SPY"),
        direction=result.get("direction", "long_short"),
        neutralize=result.get("neutralize", "none"),
        survivorship_corrected=bool(result.get("survivorship_corrected")),
        headline_cells=headline_cells,
        equity_json=json.dumps(equity),
        dd_json=json.dumps(dd),
        monthly_returns=bool(monthly),
        monthly_table=monthly_table,
        raw_metrics=raw_metrics,
        raw_json=json.dumps(result, default=str),
    )
