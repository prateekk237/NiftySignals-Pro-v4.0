"""
IndicatorService — wraps original indicators.py with memoization.
Caches indicator results to avoid recomputation on every request.
"""

import hashlib
import logging
import pandas as pd
from typing import Dict, Optional

from indicators import (
    add_all_indicators,
    get_indicator_signals,
    calc_cpr,
    calc_orb_levels,
)

logger = logging.getLogger(__name__)


class IndicatorService:
    """Indicator computation with result caching."""

    def __init__(self):
        self._last_hash: str = ""
        self._cached_df: Optional[pd.DataFrame] = None
        self._cached_signals: Optional[Dict] = None

    def _df_hash(self, df: pd.DataFrame) -> str:
        """Quick hash of last 3 rows to detect changes."""
        if df.empty:
            return ""
        tail = df.tail(3)
        raw = f"{tail['Close'].values.tobytes()}{tail.index[-1]}"
        return hashlib.md5(raw.encode()).hexdigest()

    def compute_indicators(self, df: pd.DataFrame, timeframe: str = "Intraday") -> pd.DataFrame:
        """Add all indicators. Returns cached result if data hasn't changed."""
        current_hash = self._df_hash(df)
        if current_hash == self._last_hash and self._cached_df is not None:
            logger.debug("Indicators cache hit — skipping recomputation")
            return self._cached_df

        logger.info("Computing all indicators...")
        result = add_all_indicators(df, timeframe)
        self._cached_df = result
        self._last_hash = current_hash
        self._cached_signals = None  # invalidate signal cache
        return result

    def get_signals(self, df: pd.DataFrame) -> Dict:
        """Extract signals from indicator DataFrame. Cached."""
        if self._cached_signals is not None:
            current_hash = self._df_hash(df)
            if current_hash == self._last_hash:
                return self._cached_signals

        signals = get_indicator_signals(df)
        self._cached_signals = signals
        return signals

    @staticmethod
    def calc_cpr(prev_high: float, prev_low: float, prev_close: float) -> Dict:
        return calc_cpr(prev_high, prev_low, prev_close)

    @staticmethod
    def calc_orb_levels(df: pd.DataFrame) -> Dict:
        return calc_orb_levels(df)


# Singleton
indicator_service = IndicatorService()
