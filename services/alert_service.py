"""
AlertService — wraps original realtime_alerts.py.
"""

import logging
from typing import Dict, List, Optional

from realtime_alerts import (
    generate_realtime_alerts,
    get_exit_recommendation,
)

logger = logging.getLogger(__name__)


class AlertService:
    """Real-time exit alert generation."""

    def generate_alerts(
        self,
        current_position: str,
        df,
        vix_current: float,
        vix_prev: float,
        pcr_current: float = 0,
        news_headlines: list = None,
        cpr_levels: dict = None,
        oi_support: list = None,
        oi_resistance: list = None,
    ) -> List[Dict]:
        try:
            return generate_realtime_alerts(
                current_position=current_position,
                df=df,
                vix_current=vix_current,
                vix_prev=vix_prev,
                pcr_current=pcr_current,
                news_headlines=news_headlines or [],
                cpr_levels=cpr_levels or {},
                oi_support=oi_support or [],
                oi_resistance=oi_resistance or [],
            )
        except Exception as e:
            logger.error(f"Alert generation failed: {e}")
            return []

    def get_exit_recommendation(
        self,
        alerts: List[Dict],
        current_position: str,
        entry_premium: float,
        current_premium: float,
    ) -> Dict:
        try:
            return get_exit_recommendation(
                alerts, current_position, entry_premium, current_premium
            )
        except Exception as e:
            logger.error(f"Exit recommendation failed: {e}")
            return {
                "action": "HOLD",
                "message": "Unable to assess — hold current position",
                "urgency": "LOW",
                "color": "#ffc107",
            }


# Singleton
alert_service = AlertService()
