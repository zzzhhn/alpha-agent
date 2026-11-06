"""Read-only, bounded metrics and pure interval evidence, without a provider."""
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import HTTPException

from alpha_agent.paper import bot_analytics as analytics

DAYS = [date(2026, 11, day) for day in (2, 3, 4, 5)]
CLOSES = {day: datetime(2026, 11, day.day, 21, tzinfo=UTC) for day in DAYS}
NOW = datetime(2026, 11, 5, 22, tzinfo=UTC)


def point(day, nav=1000, spy=100, **overrides):
    return {'as_of_date': day, 'portfolio_value': nav, 'benchmark_close': spy,
            'valuation_quality': 'session_close', 'valued_at': CLOSES[day]} | overrides


def test_all_cash_with_matched_spy_has_zero_bot_return_and_drawdown():
    result = analytics.calculate_history([
        point(DAYS[0], spy=100, valuation_quality='cash_only'),
        point(DAYS[1], spy=105, valuation_quality='cash_only'),
    ], CLOSES, NOW)
    window = result['matched_window']
    assert window['complete'] is True
    assert window['bot_return_pct'] == 0
    assert window['cash_return_pct'] == 0
    assert window['spy_return_pct'] == pytest.approx(5)
    assert window['bot_max_drawdown_pct'] == 0
    assert result['average_nav'] == 1000


def test_no_quotes_never_replaces_nav_or_spy_with_cash_or_zero():
    result = analytics.calculate_history([
        point(DAYS[0], nav=None, spy=None, valuation_quality='partial'),
        point(DAYS[1], nav=None, spy=None, valuation_quality='partial'),
    ], CLOSES, NOW)
    assert result['history']['null_nav_count'] == 2
    assert result['history']['valid_nav_count'] == 0
    window = result['matched_window']
    assert window['bot_return_pct'] is None
    assert window['spy_return_pct'] is None
    assert window['cash_return_pct'] is None
    assert window['bot_max_drawdown_pct'] is None


def test_valid_cash_only_history_without_spy_is_not_a_matched_comparison():
    result = analytics.calculate_history([
        point(DAYS[0], spy=None, valuation_quality='cash_only'),
        point(DAYS[1], spy=None, valuation_quality='cash_only'),
    ], CLOSES, NOW)
    assert result['history']['valid_nav_count'] == 2
    assert result['matched_window']['reason'] == 'insufficient_common_observations'
    assert result['matched_window']['bot_return_pct'] is None


def test_matched_common_window_does_not_use_unmatched_first_or_last_samples():
    result = analytics.calculate_history([
        point(DAYS[0], nav=1000, spy=None),
        point(DAYS[1], nav=900, spy=100),
        point(DAYS[2], nav=990, spy=102),
        point(DAYS[3], nav=None, spy=110, valuation_quality='partial'),
    ], CLOSES, NOW)
    window = result['matched_window']
    assert window['start_date'] == DAYS[1].isoformat()
    assert window['end_date'] == DAYS[2].isoformat()
    assert window['bot_return_pct'] == pytest.approx(10)
    assert window['spy_return_pct'] == pytest.approx(2)
    assert result['history']['sample_count'] == 4
    assert result['history']['valid_nav_count'] == 3
    assert result['history']['null_nav_count'] == 1


@pytest.mark.parametrize('middle', [None, point(DAYS[1], nav=None), point(DAYS[1], spy=None)])
def test_missing_or_null_middle_day_keeps_endpoint_return_but_withholds_drawdown(middle):
    rows = [point(DAYS[0], nav=1000), point(DAYS[2], nav=900)]
    if middle is not None:
        rows.append(middle)
    result = analytics.calculate_history(rows, CLOSES, NOW)
    window = result['matched_window']
    assert window['bot_return_pct'] == pytest.approx(-10)
    assert window['missing_sessions'] == 1
    assert window['expected_sessions'] == 3
    assert window['complete'] is False
    assert window['bot_max_drawdown_pct'] is None
    assert result['average_nav'] is None


def test_daily_close_drawdown_is_positive_peak_to_trough_magnitude():
    result = analytics.calculate_history([
        point(DAYS[0], nav=100), point(DAYS[1], nav=120),
        point(DAYS[2], nav=90), point(DAYS[3], nav=110),
    ], CLOSES, NOW)
    assert result['matched_window']['bot_max_drawdown_pct'] == pytest.approx(25)
    assert result['matched_window']['bot_return_pct'] == pytest.approx(10)


@pytest.mark.parametrize('overrides', [
    {'valuation_quality': 'fresh'}, {'valuation_quality': None},
    {'valuation_quality': 'partial'}, {'portfolio_value': float('nan')},
    {'portfolio_value': 0}, {'valued_at': None},
    {'valued_at': CLOSES[DAYS[1]] - timedelta(hours=2)},
    {'valued_at': NOW + timedelta(hours=1)},
])
def test_incomplete_intraday_unproven_or_invalid_observations_are_not_close_endpoints(overrides):
    result = analytics.calculate_history([
        point(DAYS[0]), point(DAYS[1], **overrides),
    ], CLOSES, NOW)
    assert result['history']['valid_nav_count'] == 1
    assert result['matched_window']['bot_return_pct'] is None


def test_cash_only_intraday_spy_is_not_treated_as_a_close_price():
    result = analytics.calculate_history([
        point(DAYS[0], valuation_quality='cash_only'),
        point(DAYS[1], valuation_quality='cash_only',
              valued_at=CLOSES[DAYS[1]] - timedelta(hours=1)),
    ], CLOSES, NOW)
    assert result['history']['valid_nav_count'] == 1
    assert result['matched_window']['spy_return_pct'] is None


class Snapshot:
    def __init__(self, rows=None, positions=None, kind='bot'):
        self.account = {'id': 22, 'user_id': 11, 'kind': kind, 'reset_count': 3, 'cash': 1000}
        self.rows = rows or []
        self.positions = positions or []
        self.calls = []
        self.transaction_options = None
        self.aggregate = {
            'filled': 2, 'pending': 1, 'failed': 1, 'expired': 1, 'cancelled': 0,
            'paid_fees': 4.0, 'undated_fills': 0, 'invalid_window_fills': 0,
            'window_gross_notional': 500.0,
        }

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self, **kwargs):
        self.transaction_options = kwargs
        yield

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        if 'FROM sim_account' in sql:
            return dict(self.account) if args == (22, 11) else None
        assert 'FROM sim_order' in sql
        assert args[:2] == (22, 3)
        assert 'cohort_id=$2' in sql
        return dict(self.aggregate)

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        if 'FROM sim_equity_daily' in sql:
            assert args == (22, 3, 367) and 'cohort_id=$2' in sql
            assert "pre_account_invalid" in sql
            return list(reversed(self.rows))[:args[2]]
        if 'FROM sim_position' in sql:
            assert args == (22, 3, 21) and 'cohort_id=$2' in sql
            return self.positions
        assert 'FROM sim_bot_run' in sql
        assert args == (22, 20)
        return [{'created_at': NOW, 'prompt_tokens': 12, 'completion_tokens': 3, 'llm_calls': 1}]

    async def execute(self, *args):
        raise AssertionError('analytics must not write')


@pytest.fixture
def clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(analytics, 'datetime', Clock)
    monkeypatch.setattr(analytics, 'xnys_sessions', lambda start, end: [day for day in DAYS if start <= day <= end])
    monkeypatch.setattr(analytics, 'xnys_close', lambda day: CLOSES[day])


async def test_read_performance_is_owner_scoped_bounded_coherent_and_costs_are_not_subtracted_twice(clock):
    book = Snapshot([point(DAYS[0], nav=1000), point(DAYS[1], nav=1100)])
    result = await analytics.read_performance(book, 11, 22)
    assert book.transaction_options == {'isolation': 'repeatable_read', 'readonly': True}
    assert result['cohort_id'] == 3
    assert result['matched_window']['bot_return_pct'] == pytest.approx(10)
    assert result['orders']['paid_fees'] == 4
    assert result['orders']['rejected'] is None
    assert result['turnover']['average_nav'] == 1050
    assert result['turnover']['ratio_pct'] == pytest.approx(500 / 1050 * 100)
    order_args = next(args for sql, args in book.calls if 'FROM sim_order' in sql)
    assert order_args[2:] == (CLOSES[DAYS[0]], CLOSES[DAYS[1]])
    assert result['valuation']['portfolio_value'] == 1000
    assert result['valuation']['exposure_pct'] == 0
    assert result['llm']['scope'] == 'recent_20_runs_account_lifetime'
    assert result['llm']['prompt_tokens'] == 12
    assert result['llm']['cost_usd'] is None
    assert result['comparators']['deterministic']['return_pct'] is None
    assert result['comparators']['deterministic']['available'] is False


@pytest.mark.parametrize('user_id,kind,code', [(99, 'bot', 404), (11, 'human', 400)])
async def test_owner_or_account_kind_failure_happens_before_ledger_reads(clock, user_id, kind, code):
    book = Snapshot(kind=kind)
    with pytest.raises(HTTPException) as error:
        await analytics.read_performance(book, user_id, 22)
    assert error.value.status_code == code
    assert len(book.calls) == 1


async def test_missing_live_marks_leave_valuation_and_exposure_null(clock):
    book = Snapshot(positions=[{
        'ticker': 'AAPL', 'qty': 1, 'avg_cost': 100, 'mark_price': None,
        'mark_at': None, 'price_quality': 'missing',
    }])
    result = await analytics.read_performance(book, 11, 22)
    assert result['valuation']['cash'] == 1000
    assert result['valuation']['portfolio_value'] is None
    assert result['valuation']['exposure_pct'] is None
    assert result['matched_window']['cash_return_pct'] is None
    assert 'window_gross_notional' not in result['orders']


async def test_undated_fills_withhold_turnover_even_when_the_daily_path_is_complete(clock):
    book = Snapshot([point(DAYS[0]), point(DAYS[1])])
    book.aggregate['undated_fills'] = 1
    result = await analytics.read_performance(book, 11, 22)
    assert result['turnover']['ratio_pct'] is None
    assert result['turnover']['gross_filled_notional'] is None
    assert result['turnover']['reason'] == 'undated_or_invalid_fills'


async def test_recent_daily_history_has_a_guard_row_and_explicit_truncation(clock):
    rows = [point(DAYS[0]) | {'as_of_date': DAYS[0] - timedelta(days=index)} for index in range(367)]
    book = Snapshot(list(reversed(rows)))
    result = await analytics.read_performance(book, 11, 22)
    assert result['history']['sample_count'] == 366
    assert result['history']['truncated'] is True


def test_zero_cash_book_has_known_zero_nav_but_no_exposure_denominator():
    result = analytics._current_valuation({'cash': 0}, [], NOW)
    assert result['portfolio_value'] == 0
    assert result['cash'] == 0
    assert result['exposure_pct'] is None


def test_unreported_usage_is_null_and_unpriced_usage_never_gets_a_zero_dollar_cost():
    result = analytics._usage([{'created_at': NOW, 'prompt_tokens': None,
                                'completion_tokens': 4, 'llm_calls': 1}])
    assert result['prompt_tokens'] is None
    assert result['completion_tokens'] == 4
    assert result['cost_usd'] is None
