import io
import json
from datetime import UTC, datetime

from scripts import run_paper_bot_worker as carrier


def test_carrier_logs_only_safe_arrival_metadata():
    env = {'BOT_SCHEDULE': 'true', 'BOT_CRON_EXPRESSION': '32,42 12,15 * * 1-5',
           'GITHUB_RUN_ID': '123', 'CRON_SECRET': 'private', 'BYOK': 'private'}
    receipt = carrier.carrier_receipt(env, datetime(2026, 11, 9, 23, 41, tzinfo=UTC))
    assert receipt['source'] == 'github_schedule'
    assert receipt['cron_expression'] == env['BOT_CRON_EXPRESSION']
    assert 'private' not in json.dumps(receipt)
    assert 'scheduled_at' not in receipt  # We cannot infer which delayed event GitHub intended.
    assert carrier.carrier_receipt(env | {'BOT_CRON_EXPRESSION': 'private'})['cron_expression'] is None


def test_late_idle_carrier_stops_after_one_request(monkeypatch, capsys):
    monkeypatch.setenv('BOT_SCHEDULE', 'true')
    monkeypatch.setenv('BOT_OPERATION', 'run')
    monkeypatch.setenv('CRON_SECRET', 'test-only')
    requests = []
    def respond(request, timeout):
        requests.append(request)
        return io.StringIO(json.dumps({'ok': True, 'active': False, 'processed': False,
                                      'scheduled': {'reason': 'outside_schedule_window', 'enqueued': 0}}))
    monkeypatch.setattr(carrier.urllib.request, 'urlopen', respond)
    carrier.main()
    assert len(requests) == 1
    assert requests[0].full_url.endswith('?schedule=true')
    output = capsys.readouterr().out
    assert 'outside_schedule_window' in output and 'test-only' not in output
