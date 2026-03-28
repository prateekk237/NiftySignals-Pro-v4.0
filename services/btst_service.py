"""
BTSTService — wraps btst_predictor.py v3 (10-factor).
"""

import logging
from typing import Dict, List
import pandas as pd

from btst_predictor import predict_next_day_gap

logger = logging.getLogger(__name__)


class BTSTService:
    """BTST gap prediction service — 10-factor system."""

    def predict_gap(
        self,
        global_data: Dict = None,
        us_futures_data: Dict = None,
        asian_data: Dict = None,
        european_data: Dict = None,
        fii_net_flow: float = 0.0,
        vix_current: float = 0.0,
        vix_prev_close: float = 0.0,
        df_today: pd.DataFrame = None,
        pcr_eod: float = 0.0,
        indicator_signals: Dict = None,
        news_score: float = 0.0,
        news_headlines: List = None,
        dxy_change: float = 0.0,
        crude_change: float = 0.0,
        nifty_close: float = 0.0,
    ) -> Dict:
        """Predict next-day gap with all 10 factors + GIFT NIFTY proxy."""
        try:
            return predict_next_day_gap(
                us_futures_data=us_futures_data,
                asian_data=asian_data,
                european_data=european_data,
                fii_net_flow=fii_net_flow,
                vix_current=vix_current,
                vix_prev_close=vix_prev_close,
                df_today=df_today,
                pcr_eod=pcr_eod,
                indicator_signals=indicator_signals,
                news_score=news_score,
                news_headlines=news_headlines,
                dxy_change=dxy_change,
                crude_change=crude_change,
                global_data=global_data,
                nifty_close=nifty_close,
            )
        except Exception as e:
            logger.error(f"BTST prediction failed: {e}")
            return {
                "prediction": "UNCERTAIN", "emoji": "⚪",
                "score": 0.0, "confidence": 0.0,
                "bullish_count": 0, "bearish_count": 0,
                "factors": {}, "factors_with_data": 0, "total_factors": 10,
            }


# Singleton
btst_service = BTSTService()
