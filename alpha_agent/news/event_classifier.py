"""Classifier that splits macro_events rows into political vs geopolitical.

A3 (2026-05-19) Phase 3 backlog. Source: synthesizer T6 polish + memory
feedback_us_equity_news_political_signal — politician statements move
markets differently from tariff/Fed/sanctions actions (the latter is
the dominant short-term mover in the 2025-26 cycle). Splitting them
gives the user separately-attributable signals and lets the fusion
weight scheme drop one without dropping the other.

Classification rules (cheap string matching; refined later if accuracy
becomes a constraint):
  - political:    politician quotes / campaign content / legislative
                  movements / individual rally posts. Author or title
                  matches the politician-keyword set.
  - geopolitical: trade / tariff / sanction / Fed / regulatory /
                  central-bank actions. Author or title matches the
                  geopolitical-keyword set.
  - other:        neither (the row is skipped from both signals).

When a row matches both sets (e.g. a politician tweets about tariffs),
geopolitical wins — the policy *action* is the market-moving content;
the political wrapping is rhetorical context.
"""
from __future__ import annotations

from typing import Literal

EventCategory = Literal["political", "geopolitical", "other"]

# Authors associated with political content (politician handles).
_POLITICAL_AUTHORS: frozenset[str] = frozenset({
    "trump", "potus", "harris", "biden", "vance", "desantis",
    "ramaswamy", "kennedy",
})

# Authors / sources associated with geopolitical content (institutions
# producing trade / monetary / regulatory action).
_GEOPOLITICAL_AUTHORS: frozenset[str] = frozenset({
    "fed", "fomc", "powell", "ofac", "treasury", "uscbp", "ustr",
    "ecb", "boj", "boe", "pboc", "sec", "ftc", "doj",
})

# Title / body keywords that surface the category even when the author
# field is generic (e.g. truth_social posts about tariffs). All entries
# lowercase; matched as substring.
_POLITICAL_KEYWORDS: frozenset[str] = frozenset({
    "campaign", "election", "senate", "house race", "primary",
    "rally", "convention", "debate stage", "midterm",
})

_GEOPOLITICAL_KEYWORDS: frozenset[str] = frozenset({
    "tariff", "sanction", "trade war", "embargo", "regulation",
    "interest rate", "rate cut", "rate hike", "rate decision",
    "monetary policy", "fomc", "fed minutes", "ceasefire",
    "ukraine", "taiwan", "iran", "north korea",
    "ban on", "export control", "antitrust",
})


def classify_event(
    author: str | None,
    title: str | None,
    body: str | None = None,
) -> EventCategory:
    """Cheap string-matching classifier. Geopolitical wins on overlap
    (the action overrides the wrapping). Returns 'other' when no keyword
    nor author matches; downstream signals filter that out."""
    author_l = (author or "").lower()
    text_l = f"{title or ''} {body or ''}".lower()

    # Geopolitical bias: action > rhetoric, so check this set first.
    if any(a in author_l for a in _GEOPOLITICAL_AUTHORS):
        return "geopolitical"
    if any(k in text_l for k in _GEOPOLITICAL_KEYWORDS):
        return "geopolitical"
    if any(a in author_l for a in _POLITICAL_AUTHORS):
        return "political"
    if any(k in text_l for k in _POLITICAL_KEYWORDS):
        return "political"
    return "other"
