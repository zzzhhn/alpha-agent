from datetime import UTC, datetime, timedelta

from alpha_agent.alerts.triage import assess_alert


def test_position_downgrade_is_decision_critical():
    result = assess_alert(
        alert_type="rating_change",
        payload={"from": "OW", "to": "UW", "source_count": 3},
        ticker="SLB",
        created_at=datetime.now(UTC) - timedelta(minutes=10),
        in_position=True,
        in_recommendation=False,
        in_watchlist=True,
    )

    assert result["severity"] == "critical"
    assert result["relevance"] == "position"
    assert result["confidence"] == "high"
    assert result["triage_score"] == 100


def test_unlinked_old_news_is_record_only():
    result = assess_alert(
        alert_type="news_velocity",
        payload={"n_24h": 12},
        ticker="XYZ",
        created_at=datetime.now(UTC) - timedelta(days=8),
        in_position=False,
        in_recommendation=False,
        in_watchlist=False,
    )

    assert result["severity"] == "info"
    assert result["relevance"] == "record"
    assert result["triage_score"] == 10
    assert result["stale"] is True


def test_market_alert_gets_market_relevance_without_portfolio_link():
    result = assess_alert(
        alert_type="iv_spike",
        payload={"iv_percentile": 92},
        ticker="SPY",
        created_at=datetime.now(UTC),
        in_position=False,
        in_recommendation=False,
        in_watchlist=False,
    )

    assert result["relevance"] == "market"
    assert result["triage_score"] == 60
