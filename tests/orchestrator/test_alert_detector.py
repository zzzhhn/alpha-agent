from alpha_agent.orchestrator.alert_detector import detect_alerts


def _card(rating="HOLD", composite=0.0, breakdown=None):
    return {"ticker": "AAPL", "rating": rating, "composite_score": composite,
            "breakdown": breakdown or []}


def test_rating_change_triggers_alert():
    prev = _card(rating="HOLD", composite=0.3)
    curr = _card(rating="OW", composite=0.6)
    alerts = detect_alerts(prev, curr)
    assert any(a["type"] == "rating_change" for a in alerts)


def test_no_rating_change_no_alert():
    prev = _card(rating="OW", composite=1.0)
    curr = _card(rating="OW", composite=1.1)
    alerts = detect_alerts(prev, curr)
    assert not any(a["type"] == "rating_change" for a in alerts)


def test_gap_3sigma_triggers_alert():
    curr = _card(breakdown=[
        {"signal": "premarket", "z": 3.5, "raw": {"gap_sigma": 3.5}}
    ])
    alerts = detect_alerts(None, curr)
    assert any(a["type"] == "gap_3sigma" for a in alerts)


def test_iv_spike_triggers_alert():
    curr = _card(breakdown=[
        {"signal": "options", "z": 0.5, "raw": {"iv_percentile": 95}}
    ])
    alerts = detect_alerts(None, curr)
    assert any(a["type"] == "iv_spike" for a in alerts)


def test_first_observation_emits_no_alerts_except_thresholds():
    """If prev is None (first time we see this ticker), only threshold-based
    alerts fire (gap_3sigma, iv_spike, news_velocity); rating_change does not."""
    curr = _card(rating="BUY", composite=2.0)
    alerts = detect_alerts(None, curr)
    assert not any(a["type"] == "rating_change" for a in alerts)
