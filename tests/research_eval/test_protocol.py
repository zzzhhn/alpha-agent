"""Synthetic chronology; the live protocol is never used to fit a strategy."""
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest

from alpha_agent.research_eval.protocol import PROTOCOL, DateRange, purged_training_dates


def test_registration_is_frozen_and_carries_unseen_warning():
    with pytest.raises(FrozenInstanceError):
        PROTOCOL.version = "changed"
    assert not PROTOCOL.historical_test_is_unseen
    assert PROTOCOL.final_forward.start > PROTOCOL.frozen_on
    assert len(PROTOCOL.fingerprint) == 64
    assert replace(PROTOCOL, version="different").fingerprint != PROTOCOL.fingerprint
    assert PROTOCOL.to_dict()["horizons"] == [1, 3, 5, 20]
    with pytest.raises(ValueError):
        replace(PROTOCOL, purge_sessions=5)
    with pytest.raises(ValueError):
        replace(PROTOCOL, family_size=1)


def test_purge_full_delayed_label_and_embargo_on_original_calendar():
    days = [date(2020, 1, 1)+timedelta(days=i) for i in range(70)]
    train, evaluation = DateRange(days[0], days[48]), DateRange(days[50], days[69])
    result = purged_training_dates(days, train, evaluation)
    assert result[-1] == days[28]  # 28+1+20=49, strictly before 50
    assert len(result) == 29
    with pytest.raises(ValueError):
        purged_training_dates(days, evaluation, train)


def test_offline_cli_roundtrip_and_missing_refusal(tmp_path):
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/research/evaluate.py"
    payload = {"sessions": ["2020-01-01", "2020-01-02", "2020-01-03"],
               "net_returns": {"tactical_v3": {"2020-01-01": .01, "2020-01-02": -.02,
                                                "2020-01-03": .01},
                               "SPY": {"2020-01-01": .0, "2020-01-03": .0}}}
    source = tmp_path / "synthetic.json"
    source.write_text(json.dumps(payload))
    result = subprocess.run([sys.executable, str(script), str(source)], cwd=root,
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["status"] == "incomplete_path"
    assert report["comparisons"][0]["summary"]["metrics"] is None
    payload["net_returns"]["SPY"]["2020-01-02"] = .0
    source.write_text(json.dumps(payload))
    result = subprocess.run([sys.executable, str(script), str(source)], cwd=root,
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["status"] == "complete"
    assert report["comparisons"][0]["horizons"]["1"][0]["dsr"]["probability"] is None
