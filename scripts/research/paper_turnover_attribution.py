#!/usr/bin/env python3
"""Replay one owner's simulated turnover; read-only DB, private details opt-in."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from pathlib import Path

import asyncpg
from dotenv import dotenv_values

from alpha_agent.market_session import xnys_close, xnys_sessions
from alpha_agent.paper.market_clock import NEW_YORK, as_utc
from alpha_agent.paper.turnover_attribution import (
    _num,
    _session_bounds,
    load_turnover_attribution,
)


def _archival_quotes(path: Path, start: date, end: date) -> dict:
    """Validate captured historical connector receipts; no outgoing calls."""
    with path.open(encoding='utf-8') as stream:
        receipt = json.load(stream)
    opening, ending = _session_bounds(start, end)
    fetched = as_utc(receipt['retrieved_at'])
    if fetched < ending:
        raise ValueError('archival quote receipt predates the terminal close')
    calendar = receipt['calendar']
    cal_start = opening.astimezone(NEW_YORK).date()
    cal_end = ending.astimezone(NEW_YORK).date()
    expected = {d.isoformat(): xnys_close(d) for d in xnys_sessions(cal_start, cal_end)}
    verified = {row['date']: datetime.fromisoformat(row['close'])
                .replace(tzinfo=NEW_YORK).astimezone(UTC) for row in calendar}
    if expected != verified:
        raise ValueError('market calendar receipt conflicts with XNYS session bounds')

    result: dict = {'retrieved_at': fetched.isoformat(), 'ex_dividends': []}
    for key, cutoff in (('opening', opening), ('terminal', ending)):
        reply = receipt[key]
        request = reply['request']
        if request['timeframe'] != '1Min' or request['feed'] != 'sip':
            raise ValueError('receipt does not attest to Alpaca SIP 1Min quotes')
        if reply['counts']['records'] != len(request['symbols']) or set(request['symbols']) != reply['bars'].keys():
            raise ValueError('incomplete archival SIP quote receipt')
        if as_utc(request['start']) != cutoff - timedelta(minutes=1) or not as_utc(request['end']) < cutoff:
            raise ValueError('receipt does not bound the final regular-session minute')
        marks = {}
        for ticker, rows in reply['bars'].items():
            if len(rows) != 1:
                raise ValueError('expected one closing-minute receipt per symbol')
            row = rows[0]
            o, h, low, close = (_num(row.get(field), positive=True) for field in ('open', 'high', 'low', 'close'))
            if (row['symbol'] != ticker or as_utc(row['timestamp']) != cutoff - timedelta(minutes=1)
                    or None in (o, h, low, close) or low > min(o, close) or h < max(o, close)
                    or _num(row.get('volume'), positive=True) is None):
                raise ValueError('invalid closing-minute OHLC receipt')
            marks[ticker] = {'price': close, 'as_of': cutoff.isoformat(),
                             'source': 'alpaca:sip:1min:raw:retrospective'}
        result[key] = {cutoff: marks}
    action_request = receipt['actions']['request']
    if (set(action_request['symbols']) != result['terminal'][ending].keys()
            or date.fromisoformat(action_request['start']) > cal_start - timedelta(days=14)
            or date.fromisoformat(action_request['end']) < cal_end + timedelta(days=14)
            or action_request.get('ca_types') is not None):
        raise ValueError('corporate action receipt does not cover the symbols and padded dates')
    for kind, rows in receipt['actions']['announcements'].items():
        for row in rows:
            effective = row.get('ex_date') or row.get('effective_date')
            if effective is None:
                raise ValueError('cannot verify effective date of reported corporate action')
            effective_date = date.fromisoformat(effective)
            if not cal_start < effective_date <= cal_end:
                continue
            rate = _num(row.get('rate'), positive=True)
            if kind != 'cash_dividends' or rate is None:
                raise ValueError('corporate action requires separate ledger reconciliation')
            result['ex_dividends'].append({'ticker': row['symbol'], 'rate': rate, 'date': effective_date})
    return result


def _dsn(path: Path | None) -> str | None:
    if path is None:
        return os.getenv('DATABASE_URL')
    # Select this one key before invoking dotenv. Never load the file into the
    # environment or even parse unrelated application secrets into a mapping.
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.lstrip().startswith(('DATABASE_URL=', 'export DATABASE_URL=')):
                return dotenv_values(stream=StringIO(line), interpolate=False).get('DATABASE_URL')
    return None


async def _report(args: argparse.Namespace) -> dict:
    dsn = _dsn(args.env_file)
    owner = os.getenv('PAPER_ATTRIBUTION_OWNER_EMAIL')
    if not dsn or not owner:
        raise ValueError('DATABASE_URL and PAPER_ATTRIBUTION_OWNER_EMAIL are required')
    conn = await asyncpg.connect(dsn, timeout=8, command_timeout=8)
    try:
        async with conn.transaction(readonly=True, isolation='repeatable_read'):
            account = await conn.fetchrow(
                "SELECT a.id,a.user_id FROM sim_account a JOIN users u ON u.id=a.user_id "
                "WHERE lower(u.email)=lower($1) AND a.kind='bot'",
                owner,
            )
            if account is None:
                raise LookupError('owner bot account not found')
            report = await load_turnover_attribution(
                conn, account['user_id'], account['id'], args.start_date, args.end_date,
                observed_at=args.observed_at, archival_quotes=args.archival_quotes,
            )
            if args.archival_quotes is not None:
                report['provenance'] = {
                    'kind': 'retrospective_market_data',
                    'retrieved_at': args.archival_quotes['retrieved_at'],
                    'marks': 'Alpaca SIP raw final regular-session one-minute bar close',
                    'trading_sessions': 'XNYS exchange_calendars checked against Alpaca market calendar',
                    'corporate_actions': 'Alpaca padded process-date query; filtered by effective/ex-date; coverage not guaranteed',
                    'fills': 'Owner-scoped current-cohort sim_order ledger; paid fees and raw fill reference evidence',
                }
            return report
    finally:
        await conn.close(timeout=3)


def _money(value: float | None) -> str:
    return '未知' if value is None else f'{value:,.2f}'


def _markdown(report: dict) -> str:
    w, totals = report['window'], report['totals']
    p = report.get('provenance', {})
    lines = ['# 模拟机器人换仓归因（私有）', '',
             f"美东 {w['start_date']} 至 {w['end_date']}；起终点（UTC）{w['start_as_of']} / {w['end_as_of']}。",
             f"事后报价取得时间：{p.get('retrieved_at', '未提供') }。报价：{p.get('marks', '原账本留存')}。",
             '同一起点持仓和现金。仅减仓按历史卖出时间和价格，股数最多减至该策略尚持有的原仓股数。',
             '主表不计分红，与原模拟账本口径一致；不是实盘成交或市场冲击测量。', '',
             '| 方案 | 期末现金 USD | 期末净值 USD | 回报 % | 相对原仓不动 USD |',
             '|---|---:|---:|---:|---:|']
    for key, label in [('actual', '实际模拟成交'), ('hold', '原仓不动'), ('reduce_only', '仅减仓')]:
        book = report['scenarios'][key]
        lines.append('| ' + ' | '.join([label, *[_money(book[field]) for field in
                                                ('cash', 'nav', 'return_pct', 'delta_vs_hold_usd')]]) + ' |')
    lines += ['', f"成交名义金额 USD {_money(totals['notional'])}，手续费 USD {_money(totals['fees'])}，"
              f"已证实滑点 USD {_money(totals['slippage_usd'])}。", '',
              '逐笔净贡献按同一终点计算，相对于跳过本笔的价格记账，不重跑后续决策。', '',
              '| 成交时间 UTC | 标的 | 方向 | 股数 | 成交价 | 原始参考价 | 期末价 | 手续费 | 滑点 | 净贡献 | 仅减仓股数 |',
              '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for t in report['trades']:
        lines.append('| ' + ' | '.join([t['filled_at'] or '未知', t['ticker'], t['side'], str(t['qty']),
                                        *[_money(t[field]) for field in ('fill_price', 'reference_price',
                                          'terminal_price', 'fee', 'slippage_usd', 'net_vs_hold_usd')],
                                        str(t['reduce_only_qty'])]) + ' |')
    if 'cash_dividend_sensitivity' in report:
        sensitivity = report['cash_dividend_sensitivity']
        lines += ['', '分红敏感性（按除息日开始前的持股估算，不改变已记录现金）：', '',
                  '| 标的 | 除息日 | 每股现金 USD | 实际成交 | 原仓不动 | 仅减仓 |',
                  '|---|---|---:|---:|---:|---:|']
        for item in sensitivity['events']:
            lines.append('| ' + ' | '.join([item['ticker'], item['ex_date'],
                          *[_money(item[key]) for key in ('rate', 'actual', 'hold', 'reduce_only')]]) + ' |')
    return '\n'.join(lines) + '\n'


def _private_write(path: Path, contents: str) -> None:
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
        stream.write(contents)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-date', type=date.fromisoformat, required=True, help='inclusive NY date')
    parser.add_argument('--end-date', type=date.fromisoformat, required=True, help='inclusive NY date')
    parser.add_argument('--env-file', type=Path, help='optional local file; only DATABASE_URL is loaded')
    parser.add_argument('--observed-at', type=datetime.fromisoformat,
                        help='optional timezone-aware replay cutoff; not a historical DB restore')
    parser.add_argument('--quote-receipt', type=Path,
                        help='optional captured historical public-market quote/actions/calendar receipts')
    parser.add_argument('--private-json', type=Path, help='write full private report to a new file (mode 0600)')
    parser.add_argument('--private-markdown', type=Path, help='write private trade table to a new file (mode 0600)')
    parser.add_argument('--details', action='store_true',
                        help='print amounts and trades to private stdout; never commit or share')
    args = parser.parse_args()
    if args.observed_at is not None and args.observed_at.utcoffset() is None:
        parser.error('--observed-at must include a UTC offset')
    try:
        args.archival_quotes = (_archival_quotes(args.quote_receipt, args.start_date, args.end_date)
                                if args.quote_receipt else None)
        report = asyncio.run(_report(args))
        if args.private_json:
            _private_write(args.private_json, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        if args.private_markdown:
            _private_write(args.private_markdown, _markdown(report))
    except Exception as exc:
        # Do not print driver exception messages that may carry connection data.
        print(f'Turnover attribution failed ({type(exc).__name__}).', file=sys.stderr)
        return 1
    if not args.details:
        report = {key: report[key] for key in ('window', 'coverage', 'reasons')}
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
