"""
BTST Position CRUD endpoints.
CRITICAL RULE: option_type and entry_premium are ALWAYS separate fields.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime
import pytz

from core.database import get_db
from models import BTSTPosition
from schemas import (
    PositionCreate, PositionExit, PositionUpdate,
    PositionResponse, PositionStats,
)

router = APIRouter(prefix="/api/positions", tags=["positions"])
IST = pytz.timezone("Asia/Kolkata")


@router.get("", response_model=List[PositionResponse])
async def list_positions(
    status: Optional[str] = Query(None, description="Filter by status: OPEN, PROFIT, LOSS, etc."),
    symbol: Optional[str] = Query(None, pattern="^(NIFTY50|BANKNIFTY)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List all BTST positions with optional filters."""
    q = db.query(BTSTPosition)
    if status:
        q = q.filter(BTSTPosition.status == status)
    if symbol:
        q = q.filter(BTSTPosition.symbol == symbol)
    q = q.order_by(BTSTPosition.id.desc())
    return q.offset(offset).limit(limit).all()


@router.get("/open", response_model=List[PositionResponse])
async def list_open_positions(db: Session = Depends(get_db)):
    """List only open positions."""
    return db.query(BTSTPosition).filter(
        BTSTPosition.status == "OPEN"
    ).order_by(BTSTPosition.id.desc()).all()


@router.get("/stats", response_model=PositionStats)
async def get_stats(
    symbol: Optional[str] = Query(None, pattern="^(NIFTY50|BANKNIFTY)$"),
    db: Session = Depends(get_db),
):
    """Aggregate stats: win rate, avg P&L, best/worst trade."""
    q = db.query(BTSTPosition)
    if symbol:
        q = q.filter(BTSTPosition.symbol == symbol)

    all_pos = q.all()
    total = len(all_pos)
    open_trades = sum(1 for p in all_pos if p.status == "OPEN")
    closed = [p for p in all_pos if p.status != "OPEN"]
    closed_count = len(closed)

    wins = sum(1 for p in closed if p.pnl_rupees and p.pnl_rupees > 0)
    losses = sum(1 for p in closed if p.pnl_rupees and p.pnl_rupees <= 0)
    win_rate = (wins / closed_count * 100) if closed_count > 0 else 0

    pnl_pcts = [p.pnl_pct for p in closed if p.pnl_pct is not None]
    avg_pnl = sum(pnl_pcts) / len(pnl_pcts) if pnl_pcts else 0
    total_pnl = sum(p.pnl_rupees for p in closed if p.pnl_rupees) or 0
    best = max(pnl_pcts) if pnl_pcts else 0
    worst = min(pnl_pcts) if pnl_pcts else 0

    gap_days = [p for p in all_pos if p.gap_day_flag == 1]
    gap_count = len(gap_days)
    gap_closed = [p for p in gap_days if p.status != "OPEN" and p.pnl_rupees]
    gap_wins = sum(1 for p in gap_closed if p.pnl_rupees > 0)
    gap_win_rate = (gap_wins / len(gap_closed) * 100) if gap_closed else 0

    return PositionStats(
        total_trades=total,
        open_trades=open_trades,
        closed_trades=closed_count,
        wins=wins,
        losses=losses,
        win_rate=round(win_rate, 1),
        avg_pnl_pct=round(avg_pnl, 2),
        total_pnl_rupees=round(total_pnl, 2),
        best_trade_pct=round(best, 2),
        worst_trade_pct=round(worst, 2),
        avg_hold_time="",  # Could compute from entry/exit dates
        gap_day_count=gap_count,
        gap_day_win_rate=round(gap_win_rate, 1),
    )


@router.post("", response_model=PositionResponse, status_code=201)
async def create_position(pos: PositionCreate, db: Session = Depends(get_db)):
    """Add a new BTST position. option_type and entry_premium are SEPARATE fields."""
    now = datetime.now(pytz.utc).isoformat()
    db_pos = BTSTPosition(
        entry_date=pos.entry_date,
        entry_time=pos.entry_time,
        symbol=pos.symbol,
        option_type=pos.option_type,         # CE or PE only
        entry_premium=pos.entry_premium,     # ₹ amount only
        strike_price=pos.strike_price,
        status="OPEN",
        prediction=pos.prediction,
        confidence=pos.confidence,
        gap_day_flag=pos.gap_day_flag,
        gap_risk_score=pos.gap_risk_score,
        gap_risk_label=pos.gap_risk_label,
        holiday_name=pos.holiday_name,
        days_to_next_trading=pos.days_to_next_trading,
        notes=pos.notes,
        created_at=now,
    )
    db.add(db_pos)
    db.commit()
    db.refresh(db_pos)
    return db_pos


@router.get("/gap-check")
async def gap_day_check():
    """Check if today/tomorrow is a gap day (weekend/holiday)."""
    now = datetime.now(IST)
    weekday = now.weekday()
    is_friday = weekday == 4
    is_weekend = weekday >= 5
    days_to_next = 3 if is_friday else 1
    risk_score = 2 if is_friday else 1
    risk_label = "MEDIUM" if is_friday else "LOW"
    recommendation = "Weekend gap risk. Use 50% normal size." if is_friday else "Normal trading day."
    return {
        "today": now.strftime("%Y-%m-%d"), "weekday": now.strftime("%A"),
        "is_friday": is_friday, "is_weekend": is_weekend,
        "days_to_next_trading": days_to_next, "risk_score": risk_score,
        "risk_label": risk_label, "recommendation": recommendation,
    }


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(position_id: int, db: Session = Depends(get_db)):
    """Get a single position by ID."""
    pos = db.query(BTSTPosition).filter(BTSTPosition.id == position_id).first()
    if not pos:
        raise HTTPException(404, f"Position {position_id} not found.")
    return pos


@router.patch("/{position_id}/exit", response_model=PositionResponse)
async def exit_position(
    position_id: int,
    exit_data: PositionExit,
    db: Session = Depends(get_db),
):
    """Exit an open position with exit premium."""
    pos = db.query(BTSTPosition).filter(BTSTPosition.id == position_id).first()
    if not pos:
        raise HTTPException(404, f"Position {position_id} not found.")
    if pos.status != "OPEN":
        raise HTTPException(400, f"Position {position_id} is already closed (status: {pos.status}).")

    now_ist = datetime.now(IST)
    pos.exit_premium = exit_data.exit_premium
    pos.exit_date = exit_data.exit_date or now_ist.strftime("%Y-%m-%d")
    pos.exit_time = exit_data.exit_time or now_ist.strftime("%H:%M")
    pos.pnl_rupees = round(exit_data.exit_premium - pos.entry_premium, 2)
    pos.pnl_pct = round((pos.pnl_rupees / pos.entry_premium) * 100, 2) if pos.entry_premium > 0 else 0

    if pos.pnl_rupees > 0:
        pos.status = "PROFIT"
    elif pos.pnl_pct <= -30:
        pos.status = "SL_HIT"
    else:
        pos.status = "LOSS"

    if exit_data.notes:
        pos.notes = (pos.notes or "") + f" | Exit: {exit_data.notes}"

    db.commit()
    db.refresh(pos)
    return pos


@router.patch("/{position_id}", response_model=PositionResponse)
async def update_position(
    position_id: int,
    update: PositionUpdate,
    db: Session = Depends(get_db),
):
    """Update notes or status override."""
    pos = db.query(BTSTPosition).filter(BTSTPosition.id == position_id).first()
    if not pos:
        raise HTTPException(404, f"Position {position_id} not found.")

    if update.notes is not None:
        pos.notes = update.notes
    if update.status is not None:
        pos.status = update.status

    db.commit()
    db.refresh(pos)
    return pos


@router.delete("/{position_id}")
async def delete_position(position_id: int, db: Session = Depends(get_db)):
    """Delete a position."""
    pos = db.query(BTSTPosition).filter(BTSTPosition.id == position_id).first()
    if not pos:
        raise HTTPException(404, f"Position {position_id} not found.")
    db.delete(pos)
    db.commit()
    return {"deleted": position_id}


# ── Sprint 6.9 — CSV Export ──────────────────────────────────
@router.get("/export/csv")
async def export_csv(
    symbol: Optional[str] = Query(None, pattern="^(NIFTY50|BANKNIFTY)$"),
    db: Session = Depends(get_db),
):
    """Export all positions as CSV."""
    from fastapi.responses import StreamingResponse
    import io, csv

    q = db.query(BTSTPosition)
    if symbol:
        q = q.filter(BTSTPosition.symbol == symbol)
    positions = q.order_by(BTSTPosition.id.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Entry Date", "Entry Time", "Symbol", "Option Type",
        "Entry Premium", "Strike", "Exit Premium", "Exit Date", "Exit Time",
        "P&L (₹)", "P&L (%)", "Status", "Prediction", "Confidence",
        "Gap Day", "Gap Risk", "Notes",
    ])
    for p in positions:
        writer.writerow([
            p.id, p.entry_date, p.entry_time, p.symbol, p.option_type,
            p.entry_premium, p.strike_price, p.exit_premium, p.exit_date,
            p.exit_time, p.pnl_rupees, p.pnl_pct, p.status, p.prediction,
            p.confidence, "Yes" if p.gap_day_flag else "No",
            p.gap_risk_label, p.notes,
        ])

    output.seek(0)
    filename = f"btst_positions_{datetime.now(IST).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Sprint 6.10 — Bulk Delete ────────────────────────────────
from pydantic import BaseModel as _BM
class BulkDeleteRequest(_BM):
    ids: list[int]

@router.post("/bulk-delete")
async def bulk_delete(req: BulkDeleteRequest, db: Session = Depends(get_db)):
    """Delete multiple positions by ID."""
    deleted = db.query(BTSTPosition).filter(
        BTSTPosition.id.in_(req.ids)
    ).delete(synchronize_session="fetch")
    db.commit()
    return {"deleted_count": deleted, "ids": req.ids}
