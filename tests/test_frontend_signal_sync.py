# tests/test_frontend_signal_sync.py
"""Frontend-vs-backend signal drift gate (roadmap step 3, phase 2).

The 3 frontend mirrors (weights-override.ts DEFAULT_WEIGHTS + ACTIVE_CAPS,
signal-horizons.ts SIGNAL_HORIZON_DAYS, signal-labels.ts label fallback) used to
be hand-maintained copies of backend constants with NO enforcement, so they
could silently drift. This gate parses those maps and asserts they equal the
backend signal registry (the single source of truth). Adding a signal to the
registry without updating the frontend now FAILS CI.

Why a parse-and-compare gate rather than TS codegen: this repo's CI runs the
Python test suite (ruff + pytest), not a frontend build, so a generated-file
freshness check would never execute. The gate enforces the same invariant
("frontend mirrors must match the registry") in the workflow that actually runs.
"""
import re
from pathlib import Path

import pytest

from alpha_agent.signals.registry import (
    default_weights,
    fusion_caps,
    signal_horizon_days,
    signal_labels,
)

_LIB = Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib"

pytestmark = pytest.mark.skipif(
    not _LIB.exists(), reason="frontend/ not present in this checkout"
)


def _strip_comments(s: str) -> str:
    return re.sub(r"//.*", "", s)


def _number_map(ts_src: str, export_name: str) -> dict[str, float]:
    m = re.search(rf"{export_name}[^=]*=\s*\{{(.*?)\}};", ts_src, re.S)
    assert m, f"could not locate {export_name} in frontend source"
    body = _strip_comments(m.group(1))
    return {k: float(v) for k, v in re.findall(r"(\w+)\s*:\s*([0-9.]+)", body)}


def _label_map(ts_src: str) -> dict[str, dict[str, str]]:
    m = re.search(r"SIGNAL_DISPLAY_LABEL_FALLBACK[^=]*=\s*\{(.*?)\n\};", ts_src, re.S)
    assert m, "could not locate SIGNAL_DISPLAY_LABEL_FALLBACK"
    body = _strip_comments(m.group(1))
    out: dict[str, dict[str, str]] = {}
    for em in re.finditer(
        r'(\w+)\s*:\s*\{\s*zh:\s*"([^"]*)",\s*en:\s*"([^"]*)"\s*\}', body
    ):
        out[em.group(1)] = {"zh": em.group(2), "en": em.group(3)}
    return out


def test_frontend_weights_match_registry():
    src = (_LIB / "weights-override.ts").read_text(encoding="utf-8")
    assert _number_map(src, "DEFAULT_WEIGHTS") == default_weights()


def test_frontend_caps_match_registry():
    src = (_LIB / "weights-override.ts").read_text(encoding="utf-8")
    assert _number_map(src, "ACTIVE_CAPS") == fusion_caps()


def test_frontend_horizons_match_registry():
    src = (_LIB / "signal-horizons.ts").read_text(encoding="utf-8")
    # signal_horizon_days() values are ints; parsed as floats -> compare numerically.
    parsed = _number_map(src, "SIGNAL_HORIZON_DAYS")
    assert parsed == {k: float(v) for k, v in signal_horizon_days().items()}


def test_frontend_labels_match_registry():
    src = (_LIB / "signal-labels.ts").read_text(encoding="utf-8")
    assert _label_map(src) == signal_labels()
