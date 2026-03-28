"""
GlobalMarketService — wraps original global_analysis.py.
Runs blocking yfinance calls in thread pool.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Tuple

from global_analysis import (
    fetch_all_global_data,
    calculate_global_score,
    analyze_india_vix,
    analyze_indian_indices,
)

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="global")


class GlobalMarketService:
    """Global market data and scoring."""

    async def fetch_all_global_data(self) -> Dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, fetch_all_global_data)

    async def analyze_indian_indices(self) -> Dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, analyze_indian_indices)

    @staticmethod
    def calculate_global_score(global_data: Dict) -> Tuple[float, str, Dict]:
        return calculate_global_score(global_data)

    @staticmethod
    def analyze_india_vix(vix_current: float, vix_history=None) -> Dict:
        return analyze_india_vix(vix_current, vix_history)


# Singleton
global_service = GlobalMarketService()
