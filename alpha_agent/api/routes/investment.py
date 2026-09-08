"""Private planning inputs and bounded, non-executing portfolio reviews."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_user

router = APIRouter(prefix="/investment", tags=["user"])


class HoldingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,11}$")
    weight_pct: float = Field(gt=0, le=100)

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class InvestmentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    horizon_months: int = Field(ge=1, le=120)
    drawdown_review_pct: float = Field(gt=0, le=80)
    review_frequency: Literal["weekly", "monthly"]
    max_position_pct: float = Field(gt=0, le=100)
    max_sector_pct: float = Field(gt=0, le=100)
    holdings_as_of: date
    holdings: list[HoldingInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def check_portfolio(self):
        if sum(h.weight_pct for h in self.holdings) > 100.00001:
            raise ValueError("Holdings exceed 100 percent")
        if len({h.ticker for h in self.holdings}) != len(self.holdings):
            raise ValueError("Duplicate ticker")
        if self.holdings_as_of > datetime.now(UTC).date():
            raise ValueError("Holdings date cannot be in the future")
        return self


async def _profile(pool, user_id: int):
    raw = await pool.fetchval("SELECT extras->'investment_profile' FROM user_preferences WHERE user_id=$1", user_id)
    return json.loads(raw) if isinstance(raw, str) else raw


@router.get("/profile")
async def get_profile(response: Response, user_id: int = Depends(require_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return {"profile": await _profile(await get_db_pool(), user_id)}


@router.post("/profile")
async def save_profile(body: InvestmentProfile, response: Response, user_id: int = Depends(require_user)):
    response.headers["Cache-Control"] = "private, no-store"
    pool = await get_db_pool()
    payload = body.model_dump(mode="json")
    await pool.execute(
        "INSERT INTO user_preferences (user_id,extras) VALUES ($1,jsonb_build_object('investment_profile',$2::jsonb)) "
        "ON CONFLICT(user_id) DO UPDATE SET extras=jsonb_set(user_preferences.extras,'{investment_profile}',$2::jsonb),updated_at=now()",
        user_id, json.dumps(payload),
    )
    return {"profile": payload}


def review_holdings(profile: InvestmentProfile, sectors: dict[str, str | None]) -> dict:
    warnings = []
    weights: dict[str, float] = {}
    unknown = []
    for holding in profile.holdings:
        if holding.weight_pct > profile.max_position_pct:
            warnings.append({"code": "position_limit", "subject": holding.ticker, "actual_pct": holding.weight_pct, "limit_pct": profile.max_position_pct})
        sector = sectors.get(holding.ticker)
        if not sector or sector.lower() == "unknown":
            unknown.append(holding.ticker)
        else:
            weights[sector] = weights.get(sector, 0) + holding.weight_pct
    for sector, weight in weights.items():
        if weight > profile.max_sector_pct:
            warnings.append({"code": "sector_limit", "subject": sector, "actual_pct": weight, "limit_pct": profile.max_sector_pct})
    return {"warnings": warnings, "unknown_sector_tickers": unknown,
            "sector_weights": weights, "unallocated_pct": max(0, 100 - sum(h.weight_pct for h in profile.holdings)),
            "holdings_age_days": (datetime.now(UTC).date() - profile.holdings_as_of).days,
            "drawdown_monitored": False, "etf_lookthrough_available": False,
            "decision": "review_only", "orders_created": 0}


@router.get("/review")
async def get_review(response: Response, user_id: int = Depends(require_user)):
    response.headers["Cache-Control"] = "private, no-store"
    pool = await get_db_pool()
    raw = await _profile(pool, user_id)
    if raw is None:
        return {"status": "profile_required"}
    profile = InvestmentProfile.model_validate(raw)
    rows = await pool.fetch("SELECT ticker,sector FROM company_profiles WHERE ticker=ANY($1::text[])", [h.ticker for h in profile.holdings])
    return {"status": "ready", **review_holdings(profile, {r["ticker"]: r["sector"] for r in rows})}


class ThesisInput(BaseModel):
    """User-authored reasoning, not an inferred recommendation or trade order."""
    model_config = ConfigDict(extra="forbid")
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,11}$")
    rationale: str = Field(min_length=1, max_length=1000)
    counterevidence: str = Field(min_length=1, max_length=1000)
    invalidation: str = Field(min_length=1, max_length=1000)
    source_notes: str = Field(min_length=1, max_length=1000)
    next_review: date
    status: Literal["watch", "review", "closed"] = "watch"
    revision: int = Field(default=0, ge=0)

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("rationale", "counterevidence", "invalidation", "source_notes")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Reasoning fields must not be blank")
        return value.strip()


@router.get("/theses")
async def get_theses(response: Response, user_id: int = Depends(require_user)):
    response.headers["Cache-Control"] = "private, no-store"
    pool = await get_db_pool()
    raw = await pool.fetchval("SELECT extras->'investment_theses' FROM user_preferences WHERE user_id=$1", user_id)
    data = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    today = datetime.now(UTC).date().isoformat()
    entries = [{**item, "review_due": item["status"] != "closed" and item["next_review"] <= today}
               for item in data.values()]
    return {"entries": sorted(entries, key=lambda item: (item["status"] == "closed", item["next_review"])),
            "source": "user_authored", "automatic_monitoring": False, "max_entries": 30}


@router.post("/theses")
async def save_thesis(body: ThesisInput, response: Response, user_id: int = Depends(require_user)):
    response.headers["Cache-Control"] = "private, no-store"
    pool = await get_db_pool()
    payload = {**body.model_dump(mode="json"), "revision": body.revision + 1,
               "updated_at": datetime.now(UTC).isoformat()}
    # One bounded document per user; atomic per-ticker merge preserves profile
    # and other entries. Revision check prevents silent multi-tab overwrites.
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("INSERT INTO user_preferences(user_id) VALUES($1) ON CONFLICT DO NOTHING", user_id)
        raw = await conn.fetchval("SELECT extras->'investment_theses' FROM user_preferences WHERE user_id=$1 FOR UPDATE", user_id)
        entries = (json.loads(raw) if isinstance(raw, str) else raw) or {}
        existing = entries.get(body.ticker)
        if (existing or {}).get("revision", 0) != body.revision:
            raise HTTPException(409, "Thesis changed in another tab. Reload before editing.")
        if existing is None and len(entries) >= 30:
            raise HTTPException(409, "The research notebook is limited to 30 tickers.")
        entries[body.ticker] = payload
        await conn.execute(
            "UPDATE user_preferences SET extras=jsonb_set(extras,'{investment_theses}',$2::jsonb),updated_at=now() WHERE user_id=$1",
            user_id, json.dumps(entries),
        )
    return {"entry": payload, "orders_created": 0}
