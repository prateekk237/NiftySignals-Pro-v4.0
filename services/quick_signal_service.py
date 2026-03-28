"""
QuickSignalService — wraps original quick_signals.py.
"""

import logging
from typing import Dict, Optional
import pandas as pd

from quick_signals import generate_quick_signal

logger = logging.getLogger(__name__)


class QuickSignalService:
    """5-min scalping signal generation."""

    def generate(
        self,
        df: pd.DataFrame,
        symbol: str,
        capital: float = 10000,
        oc_df: pd.DataFrame = None,
        nearest_expiry: str = "",
    ) -> Dict:
        try:
            return generate_quick_signal(
                df, symbol, capital, oc_df, nearest_expiry
            )
        except Exception as e:
            logger.error(f"Quick signal generation failed: {e}")
            return {
                "has_signal": False,
                "action": "NONE",
                "reason": f"Error: {str(e)[:100]}",
                "supertrend": {"signal": 0, "detail": "N/A"},
                "vwap": {"signal": 0, "detail": "N/A"},
                "rsi": {"signal": 0, "detail": "N/A"},
                "adx": 0,
                "timestamp": "",
            }


# Singleton
quick_signal_service = QuickSignalService()
