"""
SignalService — wraps original signal_engine.py.
"""

import logging
from typing import Dict, Optional, Tuple
import pandas as pd

from signal_engine import (
    calculate_confluence_score,
    generate_trade_recommendation,
    select_best_strategy,
)

logger = logging.getLogger(__name__)


class SignalService:
    """Trade signal computation."""

    def calculate_confluence(
        self,
        indicator_signals: Dict,
        pcr_data: Optional[dict] = None,
        oi_bias: str = "NEUTRAL",
        news_score: float = 0.0,
        vix_level: float = 0.0,
        global_score: float = 0.0,
        vix_signal_score: float = 0.0,
    ) -> Tuple[float, str, Dict[str, float]]:
        """Calculate confluence score from all signal sources."""
        return calculate_confluence_score(
            indicator_signals=indicator_signals,
            pcr_data=pcr_data,
            oi_bias=oi_bias,
            news_score=news_score,
            vix_level=vix_level,
            global_score=global_score,
            vix_signal_score=vix_signal_score,
        )

    def generate_trade(
        self,
        symbol: str,
        current_price: float,
        confluence_score: float,
        signal_label: str,
        df: pd.DataFrame,
        oc_df: pd.DataFrame = None,
        vix_level: float = 15.0,
        capital: float = 10000,
        timeframe: str = "Intraday",
    ) -> Dict:
        """Generate actionable trade recommendation."""
        return generate_trade_recommendation(
            symbol=symbol,
            current_price=current_price,
            confluence_score=confluence_score,
            signal_label=signal_label,
            df=df,
            oc_df=oc_df,
            vix_level=vix_level,
            capital=capital,
            timeframe=timeframe,
        )

    def get_best_strategies(self, vix, pcr, adx, timeframe, is_expiry_day=False):
        return select_best_strategy(vix, pcr, adx, timeframe, is_expiry_day)


# Singleton
signal_service = SignalService()
