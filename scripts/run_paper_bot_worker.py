"""GitHub wake carrier. Only CRON_SECRET, never user model credentials."""
import json
import os
import time
import urllib.request
from urllib.parse import urlencode
from datetime import UTC, datetime


def carrier_receipt(env, now=None):
    """Arrival evidence, not a guessed scheduled timestamp or latency."""
    expression = env.get('BOT_CRON_EXPRESSION', '')
    allowed = {'2,12 10 * * 1-5', '32,42 12,15 * * 1-5'}
    run_id = env.get('GITHUB_RUN_ID', '')
    return {
        'event': 'paper_bot_carrier',
        'source': 'github_schedule' if env.get('BOT_SCHEDULE') == 'true' else 'workflow_dispatch',
        'observed_at': (now or datetime.now(UTC)).isoformat(),
        'cron_expression': expression if expression in allowed else None,
        'schedule_timezone': 'America/New_York',
        'github_run_id': run_id if run_id.isdigit() else None,
    }


def main():
    deadline = time.monotonic() + 14 * 60
    schedule = os.environ.get('BOT_SCHEDULE', 'false')
    operation = os.environ.get('BOT_OPERATION', 'run')
    suffix = {'market_probe': '/market_probe', 'valuation_refresh': '/valuation'}.get(operation, f'?schedule={schedule}')
    if operation == 'market_probe':
        suffix += '?' + urlencode({'ticker': os.environ.get('BOT_PROBE_TICKER') or 'SPY'})
    print(json.dumps(carrier_receipt(os.environ)), flush=True)
    while time.monotonic() < deadline:
        request = urllib.request.Request(
            f'https://alpha-api.bobbyzhong.com/api/cron/paper_bot{suffix}',
            method='POST', headers={'Authorization': 'Bearer ' + os.environ['CRON_SECRET']})
        with urllib.request.urlopen(request, timeout=280) as response:
            result = json.load(response)
        if operation in {'market_probe', 'valuation_refresh'}:
            print(json.dumps(result), flush=True)
            break
        # No private account, research or trading payloads in GitHub logs.
        log = {k: result.get(k) for k in ('ok', 'processed', 'active', 'status', 'stage')}
        scheduled = result.get('scheduled') or {}
        log['schedule'] = {k: scheduled.get(k) for k in (
            'reason', 'enqueued', 'deduplicated', 'observed_accounts', 'missed_observations',
            'observed_at', 'session_date', 'window_open', 'market_open')}
        print(json.dumps(log), flush=True)
        if not result.get('ok'):
            raise RuntimeError('paper bot worker rejected request')
        if not result.get('active'):
            break
        schedule = 'false'
        suffix = '?schedule=false'
        time.sleep(20 if result.get('stage') == 'settling' else 2)
    else:
        raise RuntimeError('paper bot worker budget exhausted; inspect persisted run status')


if __name__ == '__main__':
    main()
