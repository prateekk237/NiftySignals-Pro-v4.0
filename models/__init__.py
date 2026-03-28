"""
Models — BTSTPosition + SignalLog (accuracy tracking).
"""

from sqlalchemy import Column, Integer, Text, Float, String
from core.database import Base


class BTSTPosition(Base):
    __tablename__ = "btst_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_date = Column(Text, nullable=False)
    entry_time = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    option_type = Column(Text, nullable=False)
    entry_premium = Column(Float, nullable=False)
    strike_price = Column(Integer, nullable=True)
    exit_premium = Column(Float, nullable=True)
    exit_date = Column(Text, nullable=True)
    exit_time = Column(Text, nullable=True)
    pnl_rupees = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    status = Column(Text, nullable=False, default="OPEN")
    prediction = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    gap_day_flag = Column(Integer, nullable=False, default=0)
    gap_risk_score = Column(Integer, nullable=False, default=1)
    gap_risk_label = Column(Text, nullable=False, default="LOW")
    holiday_name = Column(Text, nullable=True)
    days_to_next_trading = Column(Integer, nullable=False, default=1)
    notes = Column(Text, nullable=True)
    created_at = Column(Text, nullable=False)

    # Trailing SL
    trailing_sl = Column(Float, nullable=True)
    highest_ltp = Column(Float, nullable=True)
    trail_stage = Column(Text, nullable=True)

    # Partial exit
    total_lots = Column(Integer, nullable=False, default=1)
    exited_lots = Column(Integer, nullable=False, default=0)
    partial_exits = Column(Text, nullable=True)


class SignalLog(Base):
    __tablename__ = "signal_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Text, nullable=False)
    signal_type = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    strike = Column(Integer, nullable=True)
    entry_premium = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    confluence_score = Column(Float, nullable=True)

    premium_30m = Column(Float, nullable=True)
    premium_60m = Column(Float, nullable=True)
    pnl_30m_pct = Column(Float, nullable=True)
    pnl_60m_pct = Column(Float, nullable=True)
    outcome = Column(Text, nullable=True)
    max_favorable = Column(Float, nullable=True)
    max_adverse = Column(Float, nullable=True)
    is_expiry_day = Column(Integer, nullable=False, default=0)

    adx_at_signal = Column(Float, nullable=True)
    vix_at_signal = Column(Float, nullable=True)
    time_of_day = Column(Text, nullable=True)
    weekday = Column(Text, nullable=True)


from models.api_key import APIKey
