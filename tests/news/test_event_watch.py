from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alpha_agent.api.routes import alerts
from alpha_agent.auth.dependencies import require_user
from alpha_agent.news import event_watch as watch
from alpha_agent.scheduling.ticks import next_unit, scheduled_slot
from api.cron.news_pipeline import rotating_news_universe

FIXTURES = Path(__file__).parent / 'fixtures'
NOW = datetime(2026, 11, 24, 17, 30, tzinfo=UTC)


def test_sec_acceptance_and_date_quality():
    raw = json.loads((FIXTURES / 'official_sec_submissions.json').read_text())
    corrected, withdrawn, date_only = watch.parse_sec('NVDA', '0001045810', raw, NOW)
    assert corrected.status == 'corrected'
    assert withdrawn.status == 'withdrawn'
    assert corrected.url.endswith('/000104581026000006/0001045810-26-000006-index.htm')
    assert corrected.published_at == NOW - timedelta(minutes=30)
    assert corrected.published_at_quality == 'sec_accepted'
    assert date_only.published_date == date(2026, 11, 23)
    assert date_only.published_at is None
    assert date_only.published_at_quality == 'date_only'
    with pytest.raises(ValueError, match='issuer'):
        watch.parse_sec('NVDA', '9999999999', raw, NOW)


def test_issuer_revisions_and_non_events():
    raw = (FIXTURES / 'official_issuer_ir.xml').read_bytes()
    first, correction, withdrawal, preview = watch.parse_ir('NVDA', raw, NOW)
    assert first.kind == 'earnings' and first.status == 'observed'
    assert first.published_at == NOW - timedelta(minutes=29)
    assert correction.kind == 'earnings' and correction.status == 'corrected'
    assert first.source_key == correction.source_key and first.fingerprint != correction.fingerprint
    assert withdrawal.status == 'withdrawn' and withdrawal.published_at_quality == 'unavailable'
    assert preview.kind == 'investor_release' and preview.published_at_quality == 'date_only'
    with pytest.raises(ValueError, match='invalid IR feed'):
        watch.parse_ir('NVDA', b'<html><h1>Forbidden</h1></html>', NOW)


def test_two_ceo_disclosures_are_separate_observations_not_corrections():
    raw = json.loads((FIXTURES / 'nvda_ceo_sec_replay.json').read_text())
    sec = watch.parse_sec('NVDA', watch.FIXED_CIK['NVDA'], raw, NOW)
    assert [e.published_at.isoformat() for e in sec] == ['2026-11-23T13:57:54+00:00', '2026-11-12T13:52:41+00:00']
    assert [e.url.rsplit('/', 1)[-1] for e in sec] == ['nvda-20261122.htm', 'nvda-20261111.htm']
    assert [e.published_at.date() for e in watch.parse_sec('NVDA', watch.FIXED_CIK['NVDA'], raw,
               datetime(2026, 11, 23, 13, 57, 53, tzinfo=UTC))] == [date(2026, 11, 12)]
    ir = watch.parse_ir('NVDA', (FIXTURES / 'nvda_ceo_ir_replay.xml').read_bytes(), NOW)
    assert [e.published_date for e in ir] == [date(2026, 11, 23), date(2026, 11, 12)]
    assert all(e.kind == 'management_change' and e.status == 'observed' for e in sec + ir)
    assert all(e.published_at is None and e.published_at_quality == 'date_only' for e in ir)
    assert len({e.source_key for e in sec + ir}) == 4


@pytest.mark.parametrize(('ticker', 'url'), [('AAPL', 'https://www.apple.com/newsroom/results/'),
                                             ('AMD', 'https://ir.amd.com/news-events/press-releases/detail/123')])
def test_ir_release_uses_verified_host_by_issuer(ticker, url):
    body = f'''<rss version="2.0"><channel><title>Example</title><item>
        <title>Issuer reports fourth quarter results</title><link>{url}</link>
        </item></channel></rss>'''.encode()
    event, = watch.parse_ir(ticker, body, NOW)
    assert event.kind == 'earnings'
    with pytest.raises(ValueError, match='invalid IR item links'):
        watch.parse_ir('NVDA', body, NOW)


@pytest.mark.parametrize(('title', 'expected'), [
    ('Issuer raises full-year financial guidance', 'guidance'),
    ('Issuer updates annual outlook', 'guidance'),
    ('Issuer completes acquisition of Example', 'merger_acquisition'),
    ('Issuer receives regulatory clearance for merger', 'regulatory'),
    ('Issuer responds to reports that it agrees to be acquired', 'investor_release'),
    ('Issuer opens new plant and shares industry outlook', 'investor_release'),
])
def test_official_title_classification_remains_coarse(title, expected):
    assert watch.issuer_event_kind(title) == expected


def test_broad_news_shards_rotate_across_exchange_days_and_holidays():
    base = [f'SYMBOL{i}' for i in range(557)]
    wednesday = datetime(2026, 11, 25, 15, tzinfo=UTC)
    first_date, first = rotating_news_universe(base, wednesday)
    assert rotating_news_universe(base, wednesday.replace(hour=19)) == (first_date, first)
    assert rotating_news_universe(base, datetime(2026, 11, 26, 19, tzinfo=UTC)) == (first_date, first)
    friday_date, friday = rotating_news_universe(base, datetime(2026, 11, 27, 15, tzinfo=UTC))
    assert friday_date == date(2026, 11, 27)
    assert friday == first[150:] + first[:150]
    assert set(first[:75]).isdisjoint(first[75:150])
    next_sessions = [datetime(2026, 11, 30, 15, tzinfo=UTC), datetime(2026, 12, 1, 15, tzinfo=UTC)]
    covered = set(first[:150] + friday[:150])
    for at in next_sessions:
        _, rotated = rotating_news_universe(base, at)
        covered.update(rotated[:150])
    assert covered == set(base)


def test_roster_rotation_budget_and_bucket_representation():
    held = 'AAPL CVX JNJ JPM WMT KO PFE GS LLY XOM TMO ORCL MRK ABBV UNH'.split()
    candidates = 'GE BLK QCOM SPGI CRM CSCO ACN NOW UBER TSLA NFLX INTC'.split()
    self_watch = 'AMZN MU IBM LRCX HPE ANET META VZ ADBE COST DIS ADI'.split()
    first = watch.select_roster(held, candidates, self_watch, 0)
    next_hour = watch.select_roster(held, candidates, self_watch, 1)
    assert first[:4] == list(watch.FIXED)
    assert len(first) == len(set(first)) == 30
    assert set(first) != set(next_hour)
    assert set(first) & set(held) and set(first) & set(candidates) and set(first) & set(self_watch)


@pytest.mark.asyncio
async def test_http_conditional_budget_and_rate_limit():
    def handler(request):
        assert 'contact@' in request.headers['User-Agent']
        if request.url.path == '/cached':
            assert request.headers['If-None-Match'] == '"v1"'
            return httpx.Response(304)
        if request.url.path == '/blocked':
            return httpx.Response(429)
        return httpx.Response(200, content=b'123')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        body, _ = await watch._get(client, 'https://data.sec.gov/cached', sec=True, prior={'etag': '"v1"'})
        assert body is None
        with pytest.raises(watch.PollBudgetExhausted):
            await watch._get(client, 'https://data.sec.gov/budget', sec=True, budget=[2])
        with pytest.raises(httpx.HTTPStatusError) as err:
            await watch._get(client, 'https://data.sec.gov/blocked', sec=True)
        assert watch._error(err.value) == 'http_429'


@pytest.mark.asyncio
async def test_postgres_first_seen_is_immutable_and_later_versions_are_distinct(applied_db):
    raw = (FIXTURES / 'official_issuer_ir.xml').read_bytes()
    first, *_ = watch.parse_ir('NVDA', raw, NOW)
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=2) as pool:
        before = await pool.fetchval('SELECT clock_timestamp()')
        assert await watch._persist(pool, 'NVDA', watch.IR, NOW, evidence=[first]) == 1
        seen = dict(await pool.fetchrow('SELECT id,first_seen_at,status FROM official_event_watch'))
        assert seen['first_seen_at'] >= before
        assert await watch._persist(pool, 'NVDA', watch.IR, NOW, evidence=[first]) == 0
        changed = replace(first, title='Issuer amends its report')
        assert await watch._persist(pool, 'NVDA', watch.IR, NOW, evidence=[changed]) == 1
        assert await watch._persist(pool, 'NVDA', watch.IR, NOW, error='http_429') == 0
        rows = [dict(r) for r in await pool.fetch('SELECT id,first_seen_at,status FROM official_event_watch ORDER BY id')]
        assert rows[0] == seen
        assert rows[1]['status'] == 'corrected' and rows[1]['first_seen_at'] >= rows[0]['first_seen_at']
        coverage = await pool.fetchrow('SELECT last_success_at,last_error FROM official_event_source')
        assert coverage['last_success_at'] >= before and coverage['last_error'] == 'http_429'


@pytest.mark.asyncio
async def test_bounded_collector_reads_mapping_and_official_feeds_without_backdating(applied_db, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(watch, 'datetime', Clock)
    monkeypatch.setattr(watch, '_roster', AsyncMock(return_value=['NVDA']))
    requests = []

    def upstream(request):
        requests.append(request.url.path)
        if request.url.path == '/files/company_tickers.json':
            return httpx.Response(200, json={'0': {'ticker': 'NVDA', 'cik_str': 1045810}})
        if request.headers.get('If-None-Match') == '"initial"':
            return httpx.Response(304)
        data = ('nvda_ceo_sec_replay.json' if request.url.host == 'data.sec.gov' else 'nvda_ceo_ir_replay.xml')
        return httpx.Response(200, content=(FIXTURES / data).read_bytes(), headers={'ETag': '"initial"'})

    transport = httpx.MockTransport(upstream)
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=2) as pool:
        before = await pool.fetchval('SELECT clock_timestamp()')
        result = await watch.collect_official_events(pool, now=NOW, transport=transport)
        assert result == {'ok': True, 'reason': 'completed', 'attempted': 2, 'events_inserted': 4, 'error_count': 0}
        assert await pool.fetchval('SELECT min(first_seen_at) FROM official_event_watch') >= before
        assert (await watch.collect_official_events(pool, now=NOW, transport=transport))['events_inserted'] == 0
        assert requests.count('/files/company_tickers.json') == 1
        assert len(requests) == 5


@pytest.mark.asyncio
async def test_read_filters_other_owner_and_keeps_media_separate():
    quote = {
        'id': 1, 'ticker': 'NVDA', 'source': watch.SEC, 'title': '8-K fixture',
        'url': 'https://www.sec.gov/filing', 'first_seen_at': NOW,
        'published_date': None, 'published_at': None, 'published_at_quality': 'unavailable',
        'kind': 'sec_filing', 'status': 'observed',
    }

    async def fetch(sql, *args):
        if 'rating_snapshot' in sql:
            return [{'ticker': 'NVDA'}]
        if 'sim_position' in sql:
            assert args == (7,)
            return [{'ticker': 'ANET'}]
        if 'official_event_source' in sql:
            assert args[0] == ['NVDA', 'ANET']
            return [{'ticker': 'NVDA', 'source': watch.SEC, 'last_error': None,
                     'last_success_at': NOW, 'last_attempt_at': NOW}]
        if 'official_event_watch' in sql:
            assert args == (['NVDA', 'ANET'], NOW, 5)
            assert 'first_seen_at <= $2' in sql
            return [quote]
        if 'news_items' in sql:
            assert args[0] == ['NVDA', 'ANET']
            return [{'id': 1, 'ticker': 'ANET', 'source': 'rss_yahoo', 'headline': 'Media fixture',
                     'url': 'https://finance.example/article', 'published_at': NOW, 'fetched_at': NOW}]
        raise AssertionError(sql)

    pool = type('Pool', (), {'fetch': staticmethod(fetch),
                             'fetchval': AsyncMock(return_value=['NVDA', 'ANET', 'PANW'])})()
    result = await watch.read_event_evidence(pool, 7, None, 5, now=NOW)
    assert result['coverage']['tracked_tickers'] == ['NVDA', 'ANET']
    assert result['coverage']['status'] == 'partial'
    assert [e['id'] for e in result['events']] == ['official:1', 'media:1']
    assert result['events'][-1]['published_at_quality'] == 'unverified'
    assert (await watch.read_event_evidence(pool, 7, 'PANW', 5, now=NOW))['coverage']['status'] == 'unsupported'


def test_api_requires_auth_validates_input_and_is_private(monkeypatch):
    app = FastAPI()
    app.include_router(alerts.router)
    client = TestClient(app)
    assert client.get('/api/alerts/events').status_code == 401
    pool = object()
    app.dependency_overrides[require_user] = lambda: 7
    monkeypatch.setattr(alerts, 'get_db_pool', AsyncMock(return_value=pool))
    reader = AsyncMock(return_value={'events': [], 'coverage': {'status': 'not_checked',
        'tracked_tickers': ['NVDA'], 'sources': [], 'as_of': NOW}})
    monkeypatch.setattr(alerts, 'read_event_evidence', reader)
    response = client.get('/api/alerts/events?ticker=nvda&limit=5')
    assert response.status_code == 200 and response.json()['coverage']['tracked_tickers'] == ['NVDA']
    assert response.headers['Cache-Control'] == 'private, no-store'
    reader.assert_awaited_once_with(pool, 7, 'NVDA', 5)
    assert client.get('/api/alerts/events?limit=51').status_code == 422


def test_scheduler_weekends_daytime_overnight_and_once_per_slot():
    saturday = datetime(2026, 11, 28, 12, 7, tzinfo=UTC)
    day = '2026-11-28'
    slot = scheduled_slot('events_watch', saturday)
    assert slot == f'{day}:12:05'
    assert slot != scheduled_slot('events_watch', saturday.replace(minute=12))
    assert scheduled_slot('events_watch', saturday.replace(hour=1, minute=7)) == f'{day}:01:00'
    kwargs = dict(now=saturday, research_day=day, slot=slot)
    assert next_unit('events_watch', **kwargs, receipts=[]).unit.name == 'events_watch'
    receipt = {'research_day': day, 'slot': slot, 'unit': 'events_watch', 'ok': False}
    assert next_unit('events_watch', **kwargs, receipts=[receipt]).reason == 'complete'
