"""Bounded first-party event observations; the feature never places orders."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from itertools import islice
from urllib.parse import urlsplit, urlunsplit

import feedparser
import httpx

from alpha_agent.data.security_identity import valid_research_symbol
from alpha_agent.signals.insider_edgar import SEC_HEADERS

SEC = 'sec_edgar'
IR = 'investor_relations'
FIXED = ('NVDA', 'AAPL', 'MSFT', 'AMD')
# Offline bootstrap of known issuers, replaced by each successful SEC map refresh.
FIXED_CIK = {'NVDA': '0001045810', 'AAPL': '0000320193', 'MSFT': '0000789019', 'AMD': '0000002488'}
IR_FEEDS = {
    'NVDA': 'https://nvidianews.nvidia.com/cats/press_release.xml',
    'AAPL': 'https://www.apple.com/newsroom/rss-feed.rss',
    'AMD': 'https://ir.amd.com/news-events/press-releases/rss',
}
IR_HOSTS = {
    'NVDA': {'nvidianews.nvidia.com', 'investor.nvidia.com'},
    'AAPL': {'www.apple.com', 'apple.com'},
    'AMD': {'ir.amd.com', 'www.amd.com', 'amd.com'},
}
SEC_MAP = 'https://www.sec.gov/files/company_tickers.json'
SEC_FORMS = frozenset({'8-K', '10-K', '10-Q', '6-K', '20-F', '40-F', 'RW', 'AW'})
MAX_TICKERS = 30
MAX_RESPONSE_BYTES = 2_000_000
MAX_DOWNLOAD_BYTES = 8_000_000
MAX_RECORDS = 12
NETWORK_BUDGET = 35
RECENT = timedelta(days=14)
TRACKED_STALE = timedelta(hours=3)
ACTIVE_STALE = timedelta(minutes=20)
_SYMBOL = re.compile(r'^[A-Z][A-Z0-9.-]{0,11}$')
_ACCESSION = re.compile(r'^\d{10}-\d{2}-\d{6}$')
_EARNINGS = re.compile(r'\b(?:reports|announces|releases)\b.{0,60}\b(?:financial|quarterly|quarter|earnings|annual) results\b', re.I)
_EARNINGS_PREVIEW = re.compile(r'\b(?:conference call|upcoming|will report|to report|date for|schedules)\b', re.I)
_MANAGEMENT = re.compile(r'\b(?:CEO transition|(?:resign(?:s|ed|ation)?|appoints|reinstates|names|steps down)\b.{0,90}\b(?:CEO|chief executive officer)|(?:CEO|chief executive officer)\b.{0,30}\b(?:resigns|steps down))\b', re.I)
_GUIDANCE = re.compile(r'\b(?:raises|lifts|lowers|cuts|updates|reaffirms|withdraws|initiates|issues|provides|suspends)\b.{0,72}\b(?:guidance|outlook)\b', re.I)
_ACQUISITION = re.compile(r'\b(?:acquires|to acquire|announces (?:the )?acquisition|completes (?:the )?acquisition|enters .{0,45} merger agreement|completes (?:the )?merger|agrees to merge|agrees to be acquired)\b', re.I)
_REGULATORY = re.compile(r'\b(?:(?:receives|secures|grants|denies|revokes)\b.{0,72}\b(?:regulatory clearance|regulatory approval|FDA approval|export licen[cs]e)|(?:SEC|DOJ|FTC|FDA|European Commission)\s+(?:approves|clears|blocks|sues|charges|opens investigation))\b', re.I)
_SPECULATION = re.compile(r'\b(?:rumou?rs?|speculation|responds to reports|media reports|potential acquisition|exploring)\b', re.I)
_CORRECTION = re.compile(r'^\s*(?:correction|corrected|correcting and replacing)\b', re.I)
_WITHDRAWAL = re.compile(r'^\s*(?:withdrawn|retracted|withdrawal notice|retraction)\b', re.I)

# An additive migration must preserve the result type of pooled prepared statements.
_SOURCE_STATE_SQL = """
    SELECT ticker, source, cik, cik_checked_at, last_attempt_at, last_success_at,
           last_error, etag, last_modified
    FROM official_event_source
    WHERE ticker = ANY($1::text[])
"""

_CANDIDATES = """
    SELECT ticker FROM rating_snapshot
    WHERE run_id = (SELECT id FROM research_run WHERE run_type='daily_close' AND status='complete'
                    ORDER BY finished_at DESC NULLS LAST,id DESC LIMIT 1)
          AND eligible AND in_universe AND rank IS NOT NULL
    ORDER BY rank,ticker LIMIT 20
"""


@dataclass(frozen=True)
class Event:
    ticker: str
    source: str
    source_key: str
    title: str
    url: str
    published_at: datetime | None
    published_date: date | None
    published_at_quality: str
    kind: str
    status: str = 'observed'

    @property
    def fingerprint(self) -> str:
        payload = (self.title, self.url, self.published_at, self.published_date,
                   self.published_at_quality, self.kind, self.status)
        return hashlib.sha256(json.dumps(payload, default=str, ensure_ascii=False).encode()).hexdigest()


def _iso_date(value) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _aware(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.astimezone(UTC) if dt.utcoffset() is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def _recent(published_at: datetime | None, published_date: date | None, now: datetime) -> bool:
    # A future source timestamp cannot become an observed disclosure yet.
    if published_at is not None:
        return now - RECENT <= published_at <= now
    return published_date is None or (now - RECENT).date() <= published_date <= now.date()


def _safe_url(value, *, hosts=None) -> str | None:
    try:
        parts = urlsplit(value or '')
        if (len(value or '') > 1500 or parts.scheme not in ('http', 'https') or not parts.hostname
                or parts.username or parts.password or any(ord(c) < 33 for c in value)):
            return None
        if hosts is not None:
            if parts.hostname not in hosts or parts.port is not None:
                return None
            return urlunsplit(('https', parts.hostname, parts.path, parts.query, ''))
        return value
    except (TypeError, ValueError):
        return None


def parse_sec(ticker: str, cik: str, payload: dict, now: datetime) -> list[Event]:
    if int(payload['cik']) != int(cik):
        raise ValueError('unexpected SEC issuer')
    recent = payload['filings']['recent']
    forms, accession, dates = (recent[field] for field in ('form', 'accessionNumber', 'filingDate'))
    if not all(isinstance(x, list) for x in (forms, accession, dates)) or not len(forms) == len(accession) == len(dates):
        raise ValueError('invalid SEC columns')
    times = recent.get('acceptanceDateTime', [])
    items = recent.get('items', [])
    documents = recent.get('primaryDocument', [])
    out = []
    for i, (form, number, filing_date) in enumerate(zip(forms, accession, dates)):
        base = form.removesuffix('/A')
        if base not in SEC_FORMS or not _ACCESSION.fullmatch(number):
            continue
        timestamp = _aware(times[i]) if i < len(times) else None
        day = _iso_date(filing_date)
        if not _recent(timestamp, day, now):
            continue
        item_codes = str(items[i]).replace(' ', '').split(',') if i < len(items) else []
        doc = documents[i] if i < len(documents) else None
        doc = doc if isinstance(doc, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,150}', doc) else f'{number}-index.htm'
        link = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{number.replace("-", "")}/{doc}'
        status = 'withdrawn' if base in ('RW', 'AW') else 'corrected' if form.endswith('/A') else 'observed'
        management = base == '8-K' and '5.02' in item_codes
        title = f'{ticker} SEC Form {form}' + (' (Item 5.02: management or board disclosure)' if management else '')
        out.append(Event(ticker, SEC, number, title, link, timestamp, day,
                         'sec_accepted' if timestamp else 'date_only' if day else 'unavailable',
                         'management_change' if management else 'sec_filing', status))
        if len(out) == MAX_RECORDS:
            break
    return out


def parse_ir(ticker: str, raw: bytes, now: datetime) -> list[Event]:
    data = feedparser.parse(raw)
    if not data.version or (data.bozo and not data.entries):
        raise ValueError('invalid IR feed')
    out = []
    for row in islice(data.entries, 60):
        title = ' '.join(unescape(row.get('title', '')).split())[:350]
        url = _safe_url(row.get('link'), hosts=IR_HOSTS.get(ticker, ()))
        if not title or not url:
            continue
        raw_time = row.get('published')
        timestamp = _aware(raw_time)
        day = _iso_date(raw_time)
        if raw_time and timestamp is None and day is None:
            try:
                dt = parsedate_to_datetime(raw_time)
                timestamp = dt.astimezone(UTC) if dt.utcoffset() is not None else None
            except (TypeError, ValueError):
                pass
        if not _recent(timestamp, day, now):
            continue
        status = 'withdrawn' if _WITHDRAWAL.match(title) else 'corrected' if _CORRECTION.match(title) else 'observed'
        kind = issuer_event_kind(title)
        source_key = hashlib.sha256(str(row.get('id') or url).encode()).hexdigest()
        out.append(Event(ticker, IR, source_key, title, url, timestamp, day,
                         'source_timestamp' if timestamp else 'date_only' if day else 'unavailable', kind, status))
        if len(out) == MAX_RECORDS:
            break
    if data.entries and not any(_safe_url(row.get('link'), hosts=IR_HOSTS.get(ticker, ())) for row in islice(data.entries, 60)):
        raise ValueError('invalid IR item links')
    return out


def issuer_event_kind(title: str) -> str:
    """Coarse fact labels for first-party titles only, never directional calls."""
    if _SPECULATION.search(title):
        return 'investor_release'
    for kind, pattern in (('management_change', _MANAGEMENT), ('guidance', _GUIDANCE),
                          ('regulatory', _REGULATORY), ('merger_acquisition', _ACQUISITION)):
        if pattern.search(title):
            return kind
    if _EARNINGS.search(title) and not _EARNINGS_PREVIEW.search(title):
        return 'earnings'
    return 'investor_release'


def select_roster(held: list[str], candidates: list[str], watch: list[str], hour: int) -> list[str]:
    """Reserve representation for each bucket; rotate overflow hourly."""
    def rotated(values, count):
        symbols = list(dict.fromkeys(t for t in values if _SYMBOL.fullmatch(t) and valid_research_symbol(t)))
        if len(symbols) > count:
            start = (hour * count) % len(symbols)
            return symbols[start:] + symbols[:start]
        return symbols

    buckets = [(held, 10), (candidates, 8), (watch, 8)]
    roster = dict.fromkeys(FIXED)
    overflow = []
    for bucket, n in buckets:
        ordered = [t for t in rotated(bucket, n) if t not in roster]
        roster.update(dict.fromkeys(ordered[:n]))
        overflow.extend(ordered[n:])
    roster.update(dict.fromkeys(overflow))
    return list(islice(roster, MAX_TICKERS))


async def _roster(pool, now: datetime) -> list[str]:
    held = await pool.fetch('''SELECT p.ticker FROM sim_position p JOIN sim_account a ON a.id=p.account_id
                             WHERE p.qty > 0 AND a.status='active' AND p.cohort_id=a.reset_count
                             GROUP BY p.ticker ORDER BY p.ticker LIMIT 120''')
    candidates = await pool.fetch(_CANDIDATES)
    watch = await pool.fetch('SELECT DISTINCT ticker FROM user_watchlist ORDER BY ticker LIMIT 120')
    return select_roster(*([r['ticker'] for r in rows] for rows in (held, candidates, watch)),
                         hour=int(now.timestamp()) // 3600)


def _parse_cik_map(raw: bytes, roster: list[str]) -> dict[str, str]:
    # SEC's current issuer aliases use '-' where some equity tickers use '.'.
    allowed = {t.replace('.', '-'): t for t in roster}
    out = {}
    data = json.loads(raw)
    if not isinstance(data, dict) or not data:
        raise ValueError('invalid SEC ticker map')
    for row in data.values():
        key = allowed.get(str(row.get('ticker', '')).upper())
        if key:
            out[key] = f'{int(row["cik_str"]):010d}'
    return out


class PollBudgetExhausted(Exception):
    pass


async def _get(client: httpx.AsyncClient, url: str, *, sec: bool = False, prior=None, budget=None):
    headers = dict(SEC_HEADERS) if sec else {}
    if prior:
        if prior.get('etag'):
            headers['If-None-Match'] = prior['etag']
        if prior.get('last_modified'):
            headers['If-Modified-Since'] = prior['last_modified']
    async with client.stream('GET', url, headers=headers) as response:
        if response.status_code == 304 and (headers.get('If-None-Match') or headers.get('If-Modified-Since')):
            validators = httpx.Headers(response.headers)
            for response_key, prior_key in (('etag', 'etag'), ('last-modified', 'last_modified')):
                if response_key not in validators and prior.get(prior_key):
                    validators[response_key] = prior[prior_key]
            return None, validators
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if budget is not None:
                budget[0] -= len(chunk)
                if budget[0] < 0:
                    raise PollBudgetExhausted
            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                raise ValueError('source payload exceeds budget')
            body.extend(chunk)
        return bytes(body), response.headers


async def _persist(pool, ticker, source, started_at, *, evidence=(), error=None, headers=None,
                   cik=None, cik_checked=None):
    etag = headers.get('etag') if headers is not None else None
    last_modified = headers.get('last-modified') if headers is not None else None
    async with pool.acquire() as conn, conn.transaction():
        inserted = 0
        # If a single poll includes multiple source versions, insert known earlier
        # publications first. This ordering is not used as their first-seen clock.
        for event in sorted(evidence, key=lambda e: e.published_at or datetime.combine(
                e.published_date or date.min, datetime.min.time(), tzinfo=UTC)):
            # Same ID + content is idempotent; a new version gets its own first_seen_at.
            # Missing feed entries never imply a withdrawal.
            result = await conn.execute('''INSERT INTO official_event_watch
                (ticker,source,source_key,content_hash,title,url,published_at,published_date,
                 published_at_quality,kind,status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                    CASE WHEN $11='observed' AND EXISTS (SELECT 1 FROM official_event_watch
                        WHERE ticker=$1 AND source=$2 AND source_key=$3) THEN 'corrected' ELSE $11 END)
                ON CONFLICT (ticker,source,source_key,content_hash) DO NOTHING''',
                event.ticker, event.source, event.source_key, event.fingerprint, event.title, event.url,
                event.published_at, event.published_date, event.published_at_quality, event.kind, event.status)
            inserted += result.endswith(' 1')
        await conn.execute('''INSERT INTO official_event_source
            (ticker,source,last_attempt_at,last_success_at,last_error,etag,last_modified,cik,cik_checked_at)
            VALUES ($1,$2,$3,CASE WHEN $4::text IS NULL THEN clock_timestamp() END,$4,$5,$6,$7,$8)
            ON CONFLICT (ticker,source) DO UPDATE SET last_attempt_at=EXCLUDED.last_attempt_at,
              last_success_at=coalesce(EXCLUDED.last_success_at,official_event_source.last_success_at),
              last_error=EXCLUDED.last_error,
              etag=CASE WHEN EXCLUDED.last_error IS NULL THEN EXCLUDED.etag ELSE official_event_source.etag END,
              last_modified=CASE WHEN EXCLUDED.last_error IS NULL THEN EXCLUDED.last_modified ELSE official_event_source.last_modified END,
              cik=CASE WHEN $8 IS NULL THEN official_event_source.cik ELSE EXCLUDED.cik END,
              cik_checked_at=coalesce(EXCLUDED.cik_checked_at,official_event_source.cik_checked_at)''',
            ticker, source, started_at, error, etag, last_modified, cik, cik_checked)
    return inserted


def _error(exc: Exception) -> str:
    return f'http_{exc.response.status_code}' if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__


async def collect_official_events(pool, *, now: datetime | None = None, transport=None) -> dict:
    now = now or datetime.now(UTC)
    roster = await _roster(pool, now)
    await pool.execute('''INSERT INTO official_event_watch_state (id,tickers,selected_at) VALUES (1,$1,$2)
        ON CONFLICT (id) DO UPDATE SET tickers=EXCLUDED.tickers,selected_at=EXCLUDED.selected_at
        WHERE official_event_watch_state.tickers IS DISTINCT FROM EXCLUDED.tickers''', roster, now)
    rows = await pool.fetch(_SOURCE_STATE_SQL, roster)
    sources = {(r['ticker'], r['source']): dict(r) for r in rows}
    floor = datetime.min.replace(tzinfo=UTC)
    sec_order = sorted(roster, key=lambda t: sources.get((t, SEC), {}).get('last_attempt_at') or floor)
    active = [(ticker, IR) for ticker in roster if ticker in IR_FEEDS] + [(ticker, SEC) for ticker in sec_order]
    lookup_due = [t for t in roster if (sources.get((t, SEC), {}).get('cik_checked_at') or floor) < now - timedelta(days=1)]
    errors = written = attempted = 0
    byte_budget = [MAX_DOWNLOAD_BYTES]
    sec_blocked = False
    if any(r.get('last_error') in ('http_403', 'http_429') and r['last_attempt_at'] > now - timedelta(minutes=30)
           for (t, s), r in sources.items() if s == SEC):
        sec_blocked = True
    try:
        async with asyncio.timeout(NETWORK_BUDGET), httpx.AsyncClient(
            timeout=httpx.Timeout(4, connect=3), follow_redirects=False, transport=transport,
        ) as client:
            mapping, map_error = None, None
            map_blocked = any(r.get('last_error') in ('map_http_403', 'map_http_429')
                              and r['last_attempt_at'] > now - timedelta(minutes=30)
                              for r in sources.values())
            if lookup_due and not sec_blocked and not map_blocked:
                try:
                    raw, _ = await _get(client, SEC_MAP, sec=True, budget=byte_budget)
                    mapping = _parse_cik_map(raw, roster)
                except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError) as exc:
                    map_error = f'map_{_error(exc)}'
                await asyncio.sleep(0.2)
            for ticker, source in active:
                prior = sources.get((ticker, source), {})
                cik, checked_at = prior.get('cik'), None
                if source == SEC and sec_blocked:
                    continue
                if source == SEC and ticker in lookup_due and mapping is not None:
                    cik, checked_at = mapping.get(ticker), now
                if source == SEC and not prior.get('cik_checked_at') and mapping is None:
                    cik = FIXED_CIK.get(ticker)
                if (source == SEC and prior.get('cik_checked_at') and mapping is None
                        and prior['cik_checked_at'] < now - timedelta(days=7)):
                    cik = None  # do not rely indefinitely on stale ticker/issuer mappings
                if source == SEC and not cik and map_blocked:
                    continue
                started = datetime.now(UTC)
                error = None
                headers = None
                evidence = []
                attempted += 1
                try:
                    if source == SEC and cik is None:
                        error = map_error or 'unmapped_issuer'
                    else:
                        if source == SEC:
                            url = f'https://data.sec.gov/submissions/CIK{cik}.json'
                        else:
                            url = IR_FEEDS[ticker]
                        conditional = prior if source == IR or cik == prior.get('cik') else None
                        raw, headers = await _get(client, url, sec=source == SEC, prior=conditional,
                                                  budget=byte_budget)
                        if raw is not None:
                            evidence = (parse_sec(ticker, cik, json.loads(raw), started) if source == SEC
                                        else parse_ir(ticker, raw, started))
                except (httpx.HTTPError, KeyError, AttributeError, TypeError, ValueError) as exc:
                    error = _error(exc)
                written += await _persist(pool, ticker, source, started, evidence=evidence, error=error,
                                          headers=headers, cik=cik, cik_checked=checked_at)
                if error:
                    errors += 1
                    if source == SEC and error in ('http_403', 'http_429'):
                        sec_blocked = True
                if source == SEC and cik is not None:
                    await asyncio.sleep(0.2)  # serial, below five SEC requests/second
    except (TimeoutError, PollBudgetExhausted):
        errors += 1
        return {'ok': True, 'reason': 'poll_budget_exhausted', 'attempted': attempted,
                'events_inserted': written, 'error_count': errors}
    return {'ok': True, 'reason': 'sec_cooldown' if sec_blocked else 'completed', 'attempted': attempted,
            'events_inserted': written, 'error_count': errors}


def _source_coverage(row: dict | None, now: datetime, *, configured=True) -> str:
    if not configured:
        return 'unsupported'
    if not row:
        return 'not_checked'
    if row['last_error']:
        return 'unavailable'
    last_success = row['last_success_at']
    if last_success is None:
        return 'not_checked'
    stale_after = ACTIVE_STALE if 12 <= now.hour <= 23 else TRACKED_STALE
    return 'healthy' if now - last_success <= stale_after else 'stale'


async def read_event_evidence(pool, user_id: int, ticker: str | None, limit: int,
                              *, now: datetime | None = None) -> dict:
    """Visible symbols are public or owned by the requesting user, never global holdings."""
    now = now or datetime.now(UTC)
    public = await pool.fetch(_CANDIDATES)
    private = await pool.fetch('''SELECT p.ticker FROM sim_position p JOIN sim_account a ON a.id=p.account_id
                  WHERE a.user_id=$1 AND a.status='active' AND p.qty>0 AND p.cohort_id=a.reset_count
                  UNION SELECT ticker FROM user_watchlist WHERE user_id=$1''', user_id)
    visible = set(FIXED) | {r['ticker'] for r in [*public, *private]}
    roster = await pool.fetchval('SELECT tickers FROM official_event_watch_state WHERE id=1')
    tracked = [t for t in (roster or FIXED) if t in visible and (ticker is None or ticker == t)]
    source_rows = await pool.fetch(_SOURCE_STATE_SQL, tracked) if tracked else []
    found = {(r['ticker'], r['source']): dict(r) for r in source_rows}
    sources = []
    for symbol in tracked:
        for source in (SEC, IR):
            row = found.get((symbol, source)) or {}
            sources.append({'ticker': symbol, 'source': source,
                            'status': _source_coverage(row, now, configured=source == SEC or symbol in IR_FEEDS),
                            'last_attempt_at': row.get('last_attempt_at'),
                            'last_success_at': row.get('last_success_at')})
    statuses = {r['status'] for r in sources} - {'unsupported'}
    if not statuses:
        coverage_status = 'unsupported'
    elif statuses == {'healthy'}:
        coverage_status = 'healthy'
    elif len(statuses) == 1:
        coverage_status = next(iter(statuses))
    else:
        coverage_status = 'partial'
    coverage = {'status': coverage_status, 'tracked_tickers': tracked, 'sources': sources, 'as_of': now}
    if not tracked:
        return {'events': [], 'coverage': coverage}
    rows = await pool.fetch('''SELECT e.id,e.ticker,e.source,e.title,e.url,e.published_at,e.published_date,
                e.published_at_quality,e.first_seen_at,e.kind,e.status,
                CASE WHEN r.event_id IS NOT NULL THEN jsonb_build_object(
                    'status',r.status,'session_date',r.session_date,'as_of',r.observed_at,'timing',r.timing,
                    'gap',r.gap - 'evidence','follow_through',r.follow_through - 'evidence',
                    'gap_reason',r.gap_reason,'follow_reason',r.follow_reason) END AS reaction
            FROM official_event_watch e
            LEFT JOIN official_event_reaction r ON r.event_id=e.id AND r.observed_at <= $2
            WHERE e.ticker=ANY($1::text[]) AND e.first_seen_at <= $2
            ORDER BY e.first_seen_at DESC,e.id DESC LIMIT $3''', tracked, now, limit)
    events = []
    for row in rows:
        item = {**dict(row), 'id': f'official:{row["id"]}', 'evidence_class': 'official'}
        if isinstance(item.get('reaction'), str):
            item['reaction'] = json.loads(item['reaction'])
        events.append(item)
    # Media is secondary, no additional upstream requests, and its publisher clock
    # is not certified by legacy ingestion. It never appears in the official table.
    media_count = min(limit - len(events), max(1, limit // 3))
    if media_count:
        rows = await pool.fetch('''SELECT id,ticker,source,headline,url,published_at,fetched_at
            FROM news_items WHERE ticker=ANY($1::text[]) AND fetched_at BETWEEN $2 AND $3
            ORDER BY fetched_at DESC,id DESC LIMIT $4''', tracked, now - timedelta(days=2), now, media_count)
        for row in rows:
            url = _safe_url(row['url'])
            if url:
                events.append({'id': f'media:{row["id"]}', 'ticker': row['ticker'], 'source': row['source'],
                               'title': row['headline'][:350], 'url': url, 'published_at': row['published_at'],
                               'published_date': None, 'published_at_quality': 'unverified',
                               'first_seen_at': row['fetched_at'], 'kind': 'media_report', 'status': 'observed',
                               'evidence_class': 'media'})
    return {'events': events, 'coverage': coverage}
