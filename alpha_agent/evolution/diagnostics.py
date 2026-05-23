"""Phase 3c diagnostic engine: pure read pass that picks the current weakest
signal, used as input to the LLM prompt template. No LLM calls here; this is
the structured 'why are we proposing?' snapshot embedded in every Diagnostic.

v1 deliberately omits worst_fold_sharpe / worst_fold_window (would require a
lightweight purged-WF on the current expression, ~500 ms; defer to v2). The
prompt template still has a stable shape because the fields exist on the
dataclass and the JSON serializer always emits them (with null values)."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from alpha_agent.signals.factor import _resolve_default_expr


@dataclass(frozen=True)
class Diagnostic:
    current_expression: str
    weak_signal: str | None
    weak_signal_ic: float | None
    worst_fold_sharpe: float | None
    worst_fold_window: tuple[str, str] | None
    symptom_summary: str

    def to_jsonable(self) -> dict:
        d = asdict(self)
        # tuple -> list so JSON encodes cleanly (json.dumps tolerates tuples
        # but downstream JS consumers prefer arrays for shape symmetry).
        if d.get("worst_fold_window") is not None:
            d["worst_fold_window"] = list(d["worst_fold_window"])
        return d


async def compute_diagnostic(pool) -> Diagnostic:
    """Read signal_ic_history (lowest 30d-window IC by most recent computed_at).
    Returns a Diagnostic; missing IC history yields weak_signal=None and a
    symptom_summary noting that the preset expression is in effect."""
    current = _resolve_default_expr()
    weak_signal: str | None = None
    weak_ic: float | None = None
    # Pick the most recent computed_at across all 30d-window rows, then the
    # lowest ic among rows at that timestamp. Two-step approach keeps the
    # query simple while still letting the diagnostic reflect the latest
    # IC computation cycle.
    row = await pool.fetchrow(
        "SELECT signal_name, ic FROM signal_ic_history "
        "WHERE window_days = 30 "
        "ORDER BY computed_at DESC, ic ASC LIMIT 1"
    )
    if row is not None:
        weak_signal = row["signal_name"]
        weak_ic = float(row["ic"])
    parts = [f"Current expression: {current}."]
    if weak_signal is not None:
        parts.append(f"Weakest 30d signal: {weak_signal} (IC={weak_ic:.4f}).")
    else:
        parts.append("No recent IC history; running on the preset expression.")
    return Diagnostic(
        current_expression=current,
        weak_signal=weak_signal,
        weak_signal_ic=weak_ic,
        worst_fold_sharpe=None,
        worst_fold_window=None,
        symptom_summary=" ".join(parts),
    )
