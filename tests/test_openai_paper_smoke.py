import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from alpha_agent.llm.base import LLMResponse
from scripts import smoke_openai_paper as smoke


def valid_response(**changes):
    values = {"content": json.dumps({"context_id": "synthetic-openai-smoke", "decision": "no_trade",
                                     "summary": "合成测试：闭市，不交易", "actions": [], "no_trade_reason": "keep_cash"}),
              "model": "gpt-6.1-sol", "prompt_tokens": 12000, "completion_tokens": 4096,
              "finish_reason": "stop", "cached_prompt_tokens": 8000, "reasoning_tokens": 3000}
    return LLMResponse(**{**values, **changes})


def fake_client(monkeypatch, response=None, error=None):
    client = SimpleNamespace(chat=AsyncMock(return_value=response or valid_response(), side_effect=error),
                             close=AsyncMock())
    build = Mock(return_value=client)
    monkeypatch.setattr(smoke, "_build_byok_client", build)
    monkeypatch.setattr(smoke, "read_key", lambda _: "fake-secret-never-print")
    return client, build


async def test_dry_run_neither_reads_credential_nor_constructs_client(monkeypatch):
    key, build = Mock(side_effect=AssertionError("credential read")), Mock(side_effect=AssertionError("client built"))
    monkeypatch.setattr(smoke, "read_key", key)
    monkeypatch.setattr(smoke, "_build_byok_client", build)
    report, exit_code = await smoke.run_smoke(smoke.parser().parse_args([]))
    assert exit_code == 0 and report["status"] == "prepared_not_called"
    assert report["llm_calls"] == 0 and report["orders_submitted"] == 0
    key.assert_not_called()
    build.assert_not_called()


async def test_live_uses_shared_prompt_and_one_bounded_call(monkeypatch):
    client, build = fake_client(monkeypatch)
    report, exit_code = await smoke.run_smoke(smoke.parser().parse_args(["--live", "--reasoning-effort", "high"]))
    assert exit_code == 0 and report["status"] == "valid_decision"
    build.assert_called_once_with("openai", "fake-secret-never-print", smoke.API_BASE, "gpt-6.1-sol", reasoning_effort="high")
    client.chat.assert_awaited_once()
    client.close.assert_awaited_once()
    expected = smoke.prepare(smoke.FIXTURE)[1]
    assert client.chat.call_args.args[0] == expected
    assert client.chat.call_args.kwargs == {"temperature": 0.3, "max_tokens": 4096}
    assert report["estimated_cost"]["amount_usd"] == pytest.approx(0.04976)
    assert report["orders_submitted"] == report["production_writes"] == 0


@pytest.mark.parametrize(("changes", "status", "parse_status"), [
    ({"finish_reason": "length"}, "output_truncated", None),
    ({"content": ""}, "empty_response", None),
    ({"content": "{"}, "invalid_decision", "invalid_json"),
    ({"content": '{"context_id":"wrong","decision":"no_trade","summary":"ok"}'}, "invalid_decision", "context_mismatch"),
    ({"finish_reason": None}, "unexpected_finish_reason", None),
    ({"model": "unknown-model"}, "unexpected_model", None),
])
async def test_incomplete_or_invalid_decisions_fail_without_retry(monkeypatch, changes, status, parse_status):
    client, _ = fake_client(monkeypatch, valid_response(**changes))
    report, exit_code = await smoke.run_smoke(smoke.parser().parse_args(["--live"]))
    assert exit_code == 1 and report["status"] == status
    assert report.get("parse_status") == parse_status
    client.chat.assert_awaited_once()
    client.close.assert_awaited_once()


async def test_missing_usage_is_not_zero_cost(monkeypatch):
    fake_client(monkeypatch, valid_response(prompt_tokens=0, completion_tokens=0, cached_prompt_tokens=None))
    report, _ = await smoke.run_smoke(smoke.parser().parse_args(["--live"]))
    assert report["estimated_cost"] is None


@pytest.mark.parametrize(("status", "code", "expected"), [
    (429, "credit_balance_exhausted", "quota_exhausted"),
    (429, "insufficient_quota", "quota_exhausted"),
    (429, "rate_limit_exceeded", "rate_limited_or_quota"),
    (401, None, "auth_or_access_failed"),
    (404, None, "model_unavailable"),
    (500, None, "request_failed"),
])
def test_error_report_never_echoes_provider_messages(monkeypatch, capsys, status, code, expected):
    error = RuntimeError("fake-secret-never-print PRIVATE_PROVIDER_BODY")
    error.status_code = status
    error.body = {"error": {"code": code, "message": str(error)}}
    client, _ = fake_client(monkeypatch, error=error)
    assert smoke.main(["--live"]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == expected
    assert "fake-secret" not in output.out + output.err
    assert "PRIVATE_PROVIDER_BODY" not in output.out + output.err
    client.chat.assert_awaited_once()
    client.close.assert_awaited_once()


async def test_missing_key_is_explicit_and_does_not_call(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    build = Mock(side_effect=AssertionError("no client without credentials"))
    monkeypatch.setattr(smoke, "_build_byok_client", build)
    report, exit_code = await smoke.run_smoke(smoke.parser().parse_args(["--live", "--env-file", str(tmp_path/"absent")]))
    assert exit_code == 2 and report["status"] == "credential_missing"
    build.assert_not_called()


async def test_timeout_is_terminal(monkeypatch):
    client, _ = fake_client(monkeypatch, error=TimeoutError("private details"))
    report, exit_code = await smoke.run_smoke(smoke.parser().parse_args(["--live"]))
    assert exit_code == 1 and report["status"] == "timeout"
    client.chat.assert_awaited_once()
    client.close.assert_awaited_once()


@pytest.mark.parametrize("kind", ["mismatch", "large", "calls", "invalid_json"])
async def test_bad_inputs_fail_before_key_read(monkeypatch, tmp_path, kind):
    value = json.loads(smoke.FIXTURE.read_text())
    if kind == "mismatch": value["context"]["context_id"] = "other"
    if kind == "large": value["context"]["text"] = "x" * 65000
    if kind == "calls": value["llm_calls"] = -1
    path = tmp_path/"input.json"
    path.write_text("{" if kind == "invalid_json" else json.dumps(value))
    key = Mock(side_effect=AssertionError("key read for invalid input"))
    monkeypatch.setattr(smoke, "read_key", key)
    report, code = await smoke.run_smoke(smoke.parser().parse_args(["--live", "--context-file", str(path)]))
    assert code == 2 and report["status"] == "invalid_input"
    key.assert_not_called()


def test_stored_json_string_envelope_is_supported(tmp_path):
    value = json.loads(smoke.FIXTURE.read_text())
    for key in ("context", "config_snapshot"): value[key] = json.dumps(value[key])
    path = tmp_path/"stored.json"
    path.write_text(json.dumps(value))
    assert smoke.prepare(path) == smoke.prepare(smoke.FIXTURE)
