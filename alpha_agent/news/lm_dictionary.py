"""Loughran-McDonald (2011) financial sentiment dictionary - bundled subset.

Citation: Loughran, T. and McDonald, B. (2011), When Is a Liability
Not a Liability? Textual Analysis, Dictionaries, and 10-Ks. Journal
of Finance, 66: 35-65.

The bundled lists are a curated subset of the full LM master
dictionary (top ~80 positive + ~150 negative high-frequency terms).
For full coverage swap to the upstream TSV.

Used as the cost-free fallback in news + political_impact signals
when a user has no BYOK key configured, so the signal continues to
contribute at low confidence rather than going silent.
"""
from __future__ import annotations

import re
from typing import Literal


_POS = frozenset([
    "accomplish", "accomplished", "achieve", "achieved", "achievement",
    "advances", "advantage", "advantageous", "advantages", "attain",
    "attractive", "beat", "beats", "benefit", "benefited", "benefiting",
    "benefits", "best", "better", "boom", "boost", "boosted", "boosting",
    "breakthrough", "breakthroughs", "brilliant", "compliment", "complimented",
    "compliments", "constructive", "create", "delight", "delighted", "despite",
    "effective", "efficient", "encouraged", "enhance", "enhanced",
    "enhancing", "enjoyable", "enthusiastic", "excellent", "exceptional",
    "excited", "exciting", "favorable", "favorably", "favored", "favoring",
    "favorite", "favourites", "gain", "gains", "great", "greater", "greatest",
    "ideal", "impress", "impressed", "impressing", "impressive", "improve",
    "improved", "improvement", "improvements", "improves", "improving",
    "innovate", "innovated", "innovates", "innovating", "innovation",
    "innovations", "innovative", "leading", "lucrative", "outperform",
    "outperformed", "outperforming", "outperforms", "outstanding", "popularity",
    "popular", "positive", "positively", "profitable", "profitably",
    "progress", "progressed", "progressing", "rebound", "rebounded",
    "rebounds", "record", "recovered", "recovery", "rewarded", "reward",
    "rising", "rose", "smooth", "solid", "strong", "stronger", "strongest",
    "succeed", "succeeded", "successes", "successful", "successfully",
    "surge", "surges", "surpass", "surpassed", "surpasses", "surpassing",
    "thrive", "thrived", "thriving", "transformed", "tremendous", "winning",
])

_NEG = frozenset([
    "abandon", "abandoned", "abandoning", "abandonment", "abnormal",
    "abnormally", "abuse", "abused", "abusing", "abusive", "accident",
    "accidents", "accusation", "accusations", "accuse", "accused", "accuses",
    "accusing", "adverse", "adversely", "adversity", "alarmed", "alarming",
    "allegation", "allegations", "alleged", "allegedly", "alleges",
    "allege", "antitrust", "argues", "arguing", "argument", "arguments",
    "arrest", "arrested", "arresting", "arrests", "bad", "badly", "bailout",
    "bankrupt", "bankruptcies", "bankruptcy", "bans", "barred", "barrier",
    "barriers", "below", "betraying", "bitter", "blame", "blamed", "blames",
    "blaming", "bottleneck", "bottlenecks", "breach", "breached", "breaches",
    "breakdown", "breakdowns", "burdensome", "calamities", "calamity",
    "cancel", "canceled", "canceling", "cancellation", "cancellations",
    "cancels", "challenge", "challenged", "challenges", "challenging",
    "claim", "claimed", "claiming", "claims", "closed", "closures", "collapse",
    "collapsed", "collapses", "collapsing", "collusion", "complain", "complained",
    "complaining", "complaint", "complaints", "complains", "concealed",
    "concealing", "concede", "conceded", "concedes", "conceding", "condemn",
    "condemnation", "condemned", "condemning", "condemns", "conflict",
    "conflicts", "confront", "confrontation", "confrontational", "confronted",
    "confronting", "confronts", "contradict", "contradicted", "contradicting",
    "contradicts", "controversial", "controversies", "controversy", "corrupt",
    "corrupted", "corrupting", "corruption", "costly", "crime", "crimes",
    "criminal", "criminals", "crises", "crisis", "critical", "criticism",
    "criticisms", "criticize", "criticized", "criticizes", "criticizing",
    "damage", "damaged", "damages", "damaging", "danger", "dangerous", "dangers",
    "decline", "declined", "declines", "declining", "default", "defaulted",
    "defaulting", "defaults", "deficit", "deficits", "delay", "delayed",
    "delaying", "delays", "deteriorate", "deteriorated", "deteriorating",
    "deterioration", "disaster", "disasters", "disclose", "disclosed",
    "discloses", "disclosing", "discontinue", "discontinued", "discontinues",
    "dismiss", "dismissed", "dismisses", "dismissing", "dispute", "disputed",
    "disputes", "disputing", "disrupt", "disrupted", "disrupting", "disruption",
    "disruptions", "disruptive", "downgrade", "downgraded", "downgrades",
    "downgrading", "downturn", "fail", "failed", "failing", "fails", "failure",
    "failures", "false", "falsely", "fault", "faults", "faulty", "fear",
    "feared", "feares", "fearing", "fears", "fraud", "frauds", "fraudulent",
    "fraudulence", "harmful", "hostile", "imprison", "imprisoned", "imprisonment",
    "investigated", "investigates", "investigating", "investigation",
    "lawsuit", "lawsuits", "layoff", "layoffs", "litigate", "litigated",
    "litigates", "litigating", "litigation", "lose", "losing", "loss", "losses",
    "lost", "miss", "missed", "misses", "missing", "negative", "negatively",
    "obstacle", "obstacles", "penalty", "penalties", "plummet", "plummeted",
    "plummets", "plummeting", "problem", "problematic", "problems", "recall",
    "recalled", "recalling", "recalls", "recession", "recessions", "reject",
    "rejected", "rejecting", "rejects", "scandal", "scandals", "severe",
    "severely", "shortfall", "shortfalls", "slow", "slowdown", "slower",
    "slowest", "slowly", "slump", "slumped", "slumping", "stagnant", "stagnate",
    "stagnation", "subpoena", "subpoenaed", "subpoenas", "suspend", "suspended",
    "suspends", "suspending", "terminated", "terminating", "termination",
    "threat", "threatened", "threatening", "threatens", "threats", "underperform",
    "underperformed", "underperforming", "underperforms", "violate", "violated",
    "violates", "violating", "violation", "violations", "warn", "warned",
    "warning", "warnings", "warns", "weak", "weakened", "weakening", "weaker",
    "weakest", "weakness", "worsen", "worsened", "worsening", "worst",
    "worried", "worries", "wrongdoing",
])


_WORD_RE = re.compile(r"\b[a-z]+\b")


def score_text(text: str) -> Literal["bullish", "bearish", "neutral"]:
    """Return discrete sentiment label for a financial text using LM 2011 dictionary.

    Rule: tokenize lowercase, count pos vs neg term hits. Output:
      pos > neg * 1.2 -> bullish
      neg > pos * 1.2 -> bearish
      else -> neutral
    The 1.2x asymmetric ratio is the conventional LM threshold to
    avoid noisy classifications on short texts.
    """
    if not text:
        return "neutral"
    words = _WORD_RE.findall(text.lower())
    pos = sum(1 for w in words if w in _POS)
    neg = sum(1 for w in words if w in _NEG)
    if pos > neg * 1.2 and pos > 0:
        return "bullish"
    if neg > pos * 1.2 and neg > 0:
        return "bearish"
    return "neutral"
