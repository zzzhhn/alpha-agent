"""GitHub wake carrier. Only CRON_SECRET, never user model credentials."""
import json
import os
import time
import urllib.request

deadline = time.monotonic() + 14 * 60
schedule = os.environ.get('BOT_SCHEDULE', 'false')
operation = os.environ.get('BOT_OPERATION', 'run')
suffix = '/market_probe' if operation == 'market_probe' else f'?schedule={schedule}'
while time.monotonic() < deadline:
    request = urllib.request.Request(
        f'https://alpha-api.bobbyzhong.com/api/cron/paper_bot{suffix}',
        method='POST', headers={'Authorization': 'Bearer ' + os.environ['CRON_SECRET']})
    with urllib.request.urlopen(request, timeout=280) as response:
        result = json.load(response)
    if operation == 'market_probe':
        print(json.dumps(result), flush=True)
        break
    # Deliberately do not print private account, research or trading payloads.
    print(json.dumps({k: result.get(k) for k in ('ok', 'processed', 'active', 'status', 'stage')}), flush=True)
    if not result.get('ok'):
        raise RuntimeError('paper bot worker rejected request')
    if not result.get('active'):
        break
    schedule = 'false'
    suffix = '?schedule=false'
    time.sleep(20 if result.get('stage') == 'settling' else 2)
else:
    raise RuntimeError('paper bot worker budget exhausted; inspect persisted run status')
