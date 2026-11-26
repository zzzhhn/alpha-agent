"""Truthful provenance and availability contracts for serverless compat telemetry (U05)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from alpha_agent.api.routes import serverless


@pytest.fixture
def serverless_client(monkeypatch):
    from api.index import app

    previous = getattr(app.state, serverless.TELEMETRY_STATE_KEY, None)
    if hasattr(app.state, serverless.TELEMETRY_STATE_KEY):
        delattr(app.state, serverless.TELEMETRY_STATE_KEY)
    try:
        with TestClient(app) as client:
            yield client, app
    finally:
        if previous is None:
            if hasattr(app.state, serverless.TELEMETRY_STATE_KEY):
                delattr(app.state, serverless.TELEMETRY_STATE_KEY)
        else:
            setattr(app.state, serverless.TELEMETRY_STATE_KEY, previous)


@pytest.mark.parametrize("ml_available", [True, False])
def test_untracked_telemetry_returns_unavailable_without_fabricated_numbers(
    serverless_client, monkeypatch, ml_available,
):
    client, _ = serverless_client
    monkeypatch.setattr(serverless, "_check_ml", lambda: ml_available)

    latency = client.get("/api/v1/pipelines/latency")
    assert latency.status_code == 200
    assert latency.headers["cache-control"] == "no-store"
    assert latency.json() == {
        "availability": "unavailable",
        "source": "untracked_serverless_compat",
        "sampled_at": None,
        "segments": [],
        "total_ms": None,
        "timestamp": None,
    }

    throughput = client.get("/api/v1/metrics/throughput")
    assert throughput.status_code == 200
    assert throughput.headers["cache-control"] == "no-store"
    assert throughput.json() == {
        "availability": "unavailable",
        "source": "untracked_serverless_compat",
        "sampled_at": None,
        "tickers_per_sec": None,
        "trades_per_sec": None,
        "features_per_sec": None,
        "timestamp": None,
    }

    config = client.get("/api/v1/system/config")
    assert config.status_code == 200
    assert config.headers["cache-control"] == "no-store"
    config_body = config.json()
    assert config_body["availability"] == "unavailable"
    assert config_body["source"] == "untracked_serverless_compat"
    assert config_body["sampled_at"] is None
    assert config_body["api_calls_24h"] is None
    assert config_body["cache_hit_rate"] is None
    assert config_body["avg_latency_ms"] is None
    assert config_body["error_count_24h"] is None
    assert isinstance(config_body["alerts"], list)

    services = client.get("/api/v1/services/health")
    assert services.status_code == 200
    assert services.headers["cache-control"] == "no-store"
    services_body = services.json()
    assert services_body["availability"] == "unavailable"
    assert services_body["sampled_at"] is None
    assert services_body["timestamp"] is None
    for item in services_body["services"]:
        assert item["availability"] == "unavailable"
        assert item["sampled_at"] is None
        assert item["latency_p95_ms"] is None
        assert item["uptime_pct_24h"] is None

    health = client.get("/api/v1/system/health")
    assert health.status_code == 200
    assert health.headers["cache-control"] == "no-store"
    health_models = health.json()["models"]
    if not health_models["model_files"]:
        assert health_models["trained"] is False
        assert health_models["last_trained"] is None


def test_injected_telemetry_reflects_distinct_measured_samples(
    serverless_client, monkeypatch,
):
    client, app = serverless_client
    monkeypatch.setattr(serverless, "_check_ml", lambda: True)

    t1 = datetime(2026, 11, 26, 14, 30, tzinfo=timezone.utc)
    setattr(app.state, serverless.TELEMETRY_STATE_KEY, {
        "pipeline_latency": {
            "source": "pipeline_profiler",
            "sampled_at": t1,
            "segments": [
                {"stage": "data_fetch", "latency_ms": 110.0},
                {"stage": "llm_decision", "latency_ms": 290.0},
            ],
        },
        "throughput": {
            "source": "batch_worker",
            "sampled_at": "2026-11-26T14:30:00+00:00",
            "tickers_per_sec": 4.25,
            "trades_per_sec": 0.5,
            "features_per_sec": 21.0,
        },
        "system_config": {
            "source": "edge_log_rollup",
            "sampled_at": "2026-11-26T14:30:00+00:00",
            "api_calls_24h": 318,
            "cache_hit_rate": 0.75,
            "avg_latency_ms": 84.3,
            "error_count_24h": 1,
            "alerts": [],
        },
        "services_health": {
            "services": {
                "fastapi": {
                    "source": "http_hist",
                    "sampled_at": "2026-11-26T14:30:00+00:00",
                    "latency_p95_ms": 38.4,
                    "uptime_pct_24h": 99.95,
                },
            },
        },
    })

    lat_1 = client.get("/api/v1/pipelines/latency").json()
    assert lat_1 == {
        "availability": "measured",
        "source": "pipeline_profiler",
        "sampled_at": "2026-11-26T14:30:00+00:00",
        "segments": [
            {"stage": "data_fetch", "latency_ms": 110.0, "percentage": 27.5},
            {"stage": "llm_decision", "latency_ms": 290.0, "percentage": 72.5},
        ],
        "total_ms": 400.0,
        "timestamp": "2026-11-26T14:30:00+00:00",
    }
    thr_1 = client.get("/api/v1/metrics/throughput").json()
    assert thr_1["availability"] == "measured"
    assert thr_1["tickers_per_sec"] == 4.25
    assert thr_1["sampled_at"] == thr_1["timestamp"] == "2026-11-26T14:30:00+00:00"

    cfg_1 = client.get("/api/v1/system/config").json()
    assert cfg_1["availability"] == "measured"
    assert cfg_1["api_calls_24h"] == 318
    assert cfg_1["avg_latency_ms"] == 84.3

    svc_1 = client.get("/api/v1/services/health").json()
    assert svc_1["availability"] == "measured"
    by_id = {s["service_id"]: s for s in svc_1["services"]}
    assert by_id["fastapi"]["availability"] == "measured"
    assert by_id["fastapi"]["latency_p95_ms"] == 38.4
    assert by_id["llm_kimi"]["availability"] == "unavailable"
    assert by_id["llm_kimi"]["latency_p95_ms"] is None

    # Injecting a second distinct snapshot updates the measured values and sample time.
    setattr(app.state, serverless.TELEMETRY_STATE_KEY, {
        "pipeline_latency": {
            "source": "pipeline_profiler",
            "sampled_at": "2026-11-26T14:35:00+00:00",
            "segments": [
                {"stage": "data_fetch", "latency_ms": 75.0},
                {"stage": "llm_decision", "latency_ms": 525.0},
            ],
        },
        "throughput": {
            "source": "batch_worker",
            "sampled_at": "2026-11-26T14:35:00+00:00",
            "tickers_per_sec": 7.5,
            "trades_per_sec": 1.25,
            "features_per_sec": 37.5,
        },
    })
    lat_2 = client.get("/api/v1/pipelines/latency").json()
    thr_2 = client.get("/api/v1/metrics/throughput").json()
    assert lat_2["availability"] == "measured"
    assert lat_2["total_ms"] == 600.0
    assert lat_2["segments"][1]["latency_ms"] == 525.0
    assert lat_2["sampled_at"] == "2026-11-26T14:35:00+00:00"
    assert thr_2["tickers_per_sec"] == 7.5
    assert thr_2["trades_per_sec"] == 1.25


def test_demo_telemetry_is_explicitly_labeled_and_incomplete_samples_stay_unavailable(
    serverless_client,
):
    client, app = serverless_client
    setattr(app.state, serverless.TELEMETRY_STATE_KEY, {
        "pipeline_latency": {
            "availability": "demo",
            "sampled_at": "2026-11-26T12:00:00+00:00",
            "segments": [{"stage": "llm_decision", "latency_ms": 900.0}],
        },
        # Missing sampled_at must not pass as a live measurement.
        "throughput": {
            "tickers_per_sec": 3.2,
            "trades_per_sec": 0.8,
            "features_per_sec": 15.6,
        },
    })

    demo_lat = client.get("/api/v1/pipelines/latency").json()
    assert demo_lat["availability"] == "demo"
    assert demo_lat["source"] == "demo_fixture"
    assert demo_lat["total_ms"] == 900.0

    incomplete_thr = client.get("/api/v1/metrics/throughput").json()
    assert incomplete_thr["availability"] == "unavailable"
    assert incomplete_thr["tickers_per_sec"] is None
    assert incomplete_thr["sampled_at"] is None


@pytest.mark.parametrize("bad_availability", ["unavailable", "stale", "bogus", 123])
def test_explicit_unavailable_or_unknown_availability_is_not_reported_measured(
    serverless_client, bad_availability,
):
    client, app = serverless_client
    ts = "2026-11-26T14:40:00+00:00"
    setattr(app.state, serverless.TELEMETRY_STATE_KEY, {
        "pipeline_latency": {
            "availability": bad_availability,
            "source": "collector_down",
            "sampled_at": ts,
            "segments": [{"stage": "llm_decision", "latency_ms": 210.0}],
            "total_ms": 210.0,
        },
        "throughput": {
            "availability": bad_availability,
            "source": "collector_down",
            "sampled_at": ts,
            "tickers_per_sec": 3.2,
            "trades_per_sec": 0.8,
            "features_per_sec": 15.6,
        },
        "system_config": {
            "availability": bad_availability,
            "source": "collector_down",
            "sampled_at": ts,
            "api_calls_24h": 100,
            "cache_hit_rate": 0.8,
            "avg_latency_ms": 42.0,
            "error_count_24h": 0,
        },
        "services_health": {
            "services": {
                "fastapi": {
                    "availability": bad_availability,
                    "source": "collector_down",
                    "sampled_at": ts,
                    "latency_p95_ms": 40.0,
                    "uptime_pct_24h": 99.9,
                },
            },
        },
    })

    lat = client.get("/api/v1/pipelines/latency").json()
    assert lat["availability"] == "unavailable"
    assert lat["source"] == "collector_down"
    assert lat["sampled_at"] is None
    assert lat["segments"] == []
    assert lat["total_ms"] is None

    thr = client.get("/api/v1/metrics/throughput").json()
    assert thr["availability"] == "unavailable"
    assert thr["tickers_per_sec"] is None
    assert thr["sampled_at"] is None

    cfg = client.get("/api/v1/system/config").json()
    assert cfg["availability"] == "unavailable"
    assert cfg["api_calls_24h"] is None
    assert cfg["sampled_at"] is None

    svc = client.get("/api/v1/services/health").json()
    assert svc["availability"] == "unavailable"
    assert svc["sampled_at"] is None
    assert svc["timestamp"] is None
    by_id = {s["service_id"]: s for s in svc["services"]}
    assert by_id["fastapi"]["availability"] == "unavailable"
    assert by_id["fastapi"]["source"] == "collector_down"
    assert by_id["fastapi"]["sampled_at"] is None
    assert by_id["fastapi"]["latency_p95_ms"] is None
    assert by_id["fastapi"]["uptime_pct_24h"] is None

    # Top-level explicit unavailable/bogus on services_health also overrides service rows.
    setattr(app.state, serverless.TELEMETRY_STATE_KEY, {
        "services_health": {
            "availability": bad_availability,
            "source": "rollup_offline",
            "sampled_at": ts,
            "services": {
                "fastapi": {
                    "availability": "measured",
                    "source": "http_hist",
                    "sampled_at": ts,
                    "latency_p95_ms": 40.0,
                    "uptime_pct_24h": 99.9,
                },
            },
        },
    })
    svc_top = client.get("/api/v1/services/health").json()
    assert svc_top["availability"] == "unavailable"
    assert svc_top["source"] == "rollup_offline"
    assert svc_top["sampled_at"] is None
    assert svc_top["timestamp"] is None
    assert all(
        item["availability"] == "unavailable" and item["latency_p95_ms"] is None
        for item in svc_top["services"]
    )


@pytest.mark.parametrize("bad_sampled_at", ["not-a-timestamp", "2026-11-26", "yesterday", 1700000000])
def test_invalid_sampled_at_strings_are_rejected_at_service_and_summary_levels(
    serverless_client, bad_sampled_at,
):
    client, app = serverless_client
    setattr(app.state, serverless.TELEMETRY_STATE_KEY, {
        "pipeline_latency": {
            "sampled_at": bad_sampled_at,
            "segments": [{"stage": "llm_decision", "latency_ms": 210.0}],
        },
        "throughput": {
            "sampled_at": bad_sampled_at,
            "tickers_per_sec": 3.2,
            "trades_per_sec": 0.8,
            "features_per_sec": 15.6,
        },
        "system_config": {
            "sampled_at": bad_sampled_at,
            "api_calls_24h": 100,
            "cache_hit_rate": 0.8,
            "avg_latency_ms": 42.0,
            "error_count_24h": 0,
        },
        "services_health": {
            "sampled_at": bad_sampled_at,
            "services": {
                "fastapi": {
                    "sampled_at": bad_sampled_at,
                    "latency_p95_ms": 40.0,
                    "uptime_pct_24h": 99.9,
                    "last_check_at": "invalid-check-ts",
                    "last_error_at": "invalid-error-ts",
                },
            },
        },
    })

    assert client.get("/api/v1/pipelines/latency").json()["availability"] == "unavailable"
    assert client.get("/api/v1/metrics/throughput").json()["availability"] == "unavailable"
    assert client.get("/api/v1/system/config").json()["availability"] == "unavailable"

    svc = client.get("/api/v1/services/health").json()
    assert svc["availability"] == "unavailable"
    assert svc["sampled_at"] is None
    assert svc["timestamp"] is None
    fastapi_svc = next(s for s in svc["services"] if s["service_id"] == "fastapi")
    assert fastapi_svc["availability"] == "unavailable"
    assert fastapi_svc["sampled_at"] is None
    assert fastapi_svc["latency_p95_ms"] is None
    assert fastapi_svc["last_error_at"] is None

    # Valid Z-suffixed and offset timestamps normalize cleanly and compare instants, not strings.
    setattr(app.state, serverless.TELEMETRY_STATE_KEY, {
        "services_health": {
            "sampled_at": bad_sampled_at,
            "services": {
                "fastapi": {
                    "sampled_at": "2026-11-26T15:00:00Z",
                    "latency_p95_ms": 31.0,
                },
                "llm_kimi": {
                    "sampled_at": "2026-11-26T10:30:00-05:00",
                    "latency_p95_ms": 420.0,
                },
            },
        },
    })
    svc_valid = client.get("/api/v1/services/health").json()
    assert svc_valid["availability"] == "measured"
    assert svc_valid["sampled_at"] == "2026-11-26T15:30:00+00:00"


@pytest.mark.parametrize("non_finite", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_floats_never_break_json_and_degrade_to_unavailable(
    serverless_client, non_finite,
):
    client, app = serverless_client
    ts = "2026-11-26T14:45:00+00:00"
    setattr(app.state, serverless.TELEMETRY_STATE_KEY, {
        "pipeline_latency": {
            "sampled_at": ts,
            "segments": [{"stage": "llm_decision", "latency_ms": non_finite}],
            "total_ms": non_finite,
        },
        "throughput": {
            "sampled_at": ts,
            "tickers_per_sec": non_finite,
            "trades_per_sec": 0.8,
            "features_per_sec": 15.6,
        },
        "system_config": {
            "sampled_at": ts,
            "api_calls_24h": non_finite,
            "cache_hit_rate": 0.8,
            "avg_latency_ms": non_finite,
            "error_count_24h": 0,
        },
        "services_health": {
            "services": {
                "fastapi": {
                    "sampled_at": ts,
                    "latency_p95_ms": non_finite,
                    "uptime_pct_24h": non_finite,
                },
            },
        },
    })

    lat_resp = client.get("/api/v1/pipelines/latency")
    assert lat_resp.status_code == 200
    assert lat_resp.json()["availability"] == "unavailable"
    assert lat_resp.json()["total_ms"] is None

    # Also verify finite segment + non-finite explicit total_ms rejects cleanly.
    app.state.serverless_telemetry["pipeline_latency"] = {
        "sampled_at": ts,
        "segments": [{"stage": "llm_decision", "latency_ms": 120.0}],
        "total_ms": non_finite,
    }
    lat_bad_total = client.get("/api/v1/pipelines/latency")
    assert lat_bad_total.status_code == 200
    assert lat_bad_total.json()["availability"] == "unavailable"
    assert lat_bad_total.json()["total_ms"] is None

    thr_resp = client.get("/api/v1/metrics/throughput")
    assert thr_resp.status_code == 200
    assert thr_resp.json()["availability"] == "unavailable"
    assert thr_resp.json()["tickers_per_sec"] is None

    cfg_resp = client.get("/api/v1/system/config")
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["availability"] == "unavailable"
    assert cfg_resp.json()["avg_latency_ms"] is None

    svc_resp = client.get("/api/v1/services/health")
    assert svc_resp.status_code == 200
    svc_body = svc_resp.json()
    assert svc_body["availability"] == "unavailable"
    assert svc_body["sampled_at"] is None
    fastapi_svc = next(s for s in svc_body["services"] if s["service_id"] == "fastapi")
    assert fastapi_svc["availability"] == "unavailable"
    assert fastapi_svc["latency_p95_ms"] is None
    assert fastapi_svc["uptime_pct_24h"] is None
