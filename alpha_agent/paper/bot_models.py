"""Small, provider-independent contracts for the simulated portfolio agent."""
from __future__ import annotations

import json
import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class BotConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider: Literal['kimi', 'openai', 'anthropic', 'ollama'] = 'kimi'
    model: str = Field(default='', max_length=120)
    instructions: str = Field(default='根据平台证据管理长期模拟组合；允许继续持有或保持现金。', max_length=2000)
    schedule_enabled: bool = False
    open_enabled: bool = True
    close_enabled: bool = True
    # First release uses two bounded scheduler windows, not arbitrary cron.
    open_offset_minutes: Literal[30] = 30
    close_offset_minutes: Literal[30] = 30
    max_daily_runs: int = Field(default=6, ge=1, le=12)
    max_positions: int = Field(default=8, ge=1, le=20)
    max_position_weight: float = Field(default=0.25, gt=0, le=1, allow_inf_nan=False)
    fee_bps: float = Field(default=10, ge=0, le=100, allow_inf_nan=False)
    slippage_bps: float = Field(default=5, ge=0, le=100, allow_inf_nan=False)
    horizon_sessions: int = Field(default=20, ge=1, le=252)
    max_research_age_sessions: int = Field(default=3, ge=0, le=20)
    min_trade_weight_delta: float = Field(default=0, ge=0, le=0.25, allow_inf_nan=False)
    max_turnover_weight: float = Field(default=2, ge=0, le=2, allow_inf_nan=False)
    cash_policy: Literal['discretionary'] = 'discretionary'


class BotAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action_id: str = Field(min_length=1, max_length=40, pattern=r'^[a-zA-Z0-9_-]+$')
    type: Literal['set_target_weight', 'cancel_order'] = 'set_target_weight'
    instrument_id: str | None = None
    target_weight: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    order_id: int | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)
    reason: str = Field(default='', max_length=600)

    @model_validator(mode='after')
    def valid_action(self):
        if self.type == 'set_target_weight' and (not self.instrument_id or self.target_weight is None):
            raise ValueError('weight action requires instrument_id and target_weight')
        if self.type == 'cancel_order' and not self.order_id:
            raise ValueError('cancel action requires order_id')
        return self


class PositionNote(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ticker: str = Field(max_length=10, pattern=r'^[A-Z0-9.^-]+$')
    note: str = Field(max_length=600)
    thesis: str = Field(default='', max_length=400)
    invalidation: str = Field(default='', max_length=400)
    review_after: date | None = None


class BotDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    context_id: str
    decision: Literal['rebalance', 'no_trade', 'research']
    summary: str = Field(max_length=1600)
    actions: list[BotAction] = Field(default_factory=list, max_length=20)
    position_notes: list[PositionNote] = Field(default_factory=list, max_length=20)
    research_tickers: list[str] = Field(default_factory=list, max_length=5)
    target_semantics: Literal['patch_targets'] = 'patch_targets'
    no_trade_reason: Literal['keep_cash', 'keep_positions', 'strategy_no_op', 'evidence_insufficient'] | None = None

    @model_validator(mode='after')
    def coherent(self):
        if self.decision != 'rebalance' and self.actions:
            raise ValueError('only rebalance may contain actions')
        if self.decision == 'rebalance' and not self.actions:
            raise ValueError('empty rebalance: use no_trade with an explicit reason')
        if len({a.action_id for a in self.actions}) != len(self.actions):
            raise ValueError('action_id must be unique')
        ids = [a.instrument_id for a in self.actions if a.type == 'set_target_weight']
        if len(set(ids)) != len(ids):
            raise ValueError('one target per instrument')
        weights = sum(a.target_weight or 0 for a in self.actions)
        if not math.isfinite(weights) or weights > 1.000001:
            raise ValueError('target weights exceed capital')
        return self


class DecisionParseError(ValueError):
    """Safe diagnostics only: never retain model text, values or error messages."""

    def __init__(self, kind: str, fields: list[str] | None = None):
        super().__init__(kind)
        self.kind = kind
        self.fields = fields or []


def parse_decision(text: str, context_id: str) -> BotDecision:
    if len(text.encode()) > 24000:
        raise DecisionParseError('output_size_exceeded')
    value = text.strip()
    if value.startswith('```'):
        value = value.partition('\n')[2].rsplit('```', 1)[0].strip()
    try:
        packet = json.loads(value)
    except json.JSONDecodeError:
        raise DecisionParseError('invalid_json') from None
    try:
        decision = BotDecision.model_validate(packet)
    except ValidationError as exc:
        allowed = set(BotDecision.model_fields) | set(BotAction.model_fields) | set(PositionNote.model_fields)
        fields = list(dict.fromkeys(
            '.'.join(str(part) if isinstance(part, int) else part if part in allowed else 'unknown_field'
                     for part in error['loc']) or 'decision'
            for error in exc.errors(include_input=False, include_context=False, include_url=False)
        ))[:6]
        raise DecisionParseError('schema_mismatch', fields) from None
    if decision.context_id != context_id:
        raise DecisionParseError('context_mismatch', ['context_id'])
    return decision
