"""
Pydantic schemas for BTST position CRUD.
CRITICAL RULE: option_type and entry_premium are ALWAYS separate fields.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


# ── Request Schemas ───────────────────────────────────────────

class PositionCreate(BaseModel):
    """Create a new BTST position."""
    entry_date: str = Field(..., description="YYYY-MM-DD")
    entry_time: str = Field(..., description="HH:MM IST")
    symbol: str = Field(..., pattern="^(NIFTY50|BANKNIFTY)$")
    option_type: str = Field(..., pattern="^(CE|PE)$", description="CE or PE only — NEVER combined with premium")
    entry_premium: float = Field(..., gt=0, description="₹ amount only — NEVER combined with option_type")
    strike_price: Optional[int] = Field(None, description="Strike price for reference")
    prediction: str = Field(...)
    confidence: float = Field(..., ge=0, le=100)
    gap_day_flag: int = Field(default=0)
    gap_risk_score: int = Field(default=1, ge=1, le=5)
    gap_risk_label: str = Field(default="LOW")
    holiday_name: Optional[str] = None
    days_to_next_trading: int = Field(default=1)
    notes: Optional[str] = None


class PositionExit(BaseModel):
    """Exit an open position."""
    exit_premium: float = Field(..., gt=0, description="₹ amount only")
    exit_date: Optional[str] = None  # defaults to today
    exit_time: Optional[str] = None  # defaults to now
    notes: Optional[str] = None


class PositionUpdate(BaseModel):
    """General update (notes, status override)."""
    notes: Optional[str] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None:
            valid = {"OPEN", "PROFIT", "LOSS", "SL_HIT", "EXPIRED", "HOLIDAY_GAP"}
            if v not in valid:
                raise ValueError(f"status must be one of {valid}")
        return v


# ── Response Schemas ──────────────────────────────────────────

class PositionResponse(BaseModel):
    """Single position response."""
    id: int
    entry_date: str
    entry_time: str
    symbol: str
    option_type: str
    entry_premium: float
    strike_price: Optional[int] = None
    exit_premium: Optional[float] = None
    exit_date: Optional[str] = None
    exit_time: Optional[str] = None
    pnl_rupees: Optional[float] = None
    pnl_pct: Optional[float] = None
    status: str
    prediction: str
    confidence: float
    gap_day_flag: int
    gap_risk_score: int
    gap_risk_label: str
    holiday_name: Optional[str] = None
    days_to_next_trading: int
    notes: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}


class PositionStats(BaseModel):
    """Aggregate stats for BTST history."""
    total_trades: int = 0
    open_trades: int = 0
    closed_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_pnl_pct: float = 0.0
    total_pnl_rupees: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    avg_hold_time: str = ""
    gap_day_count: int = 0
    gap_day_win_rate: float = 0.0
