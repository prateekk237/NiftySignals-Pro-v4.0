"""
AsyncDataFetcher — wraps original data_fetcher.py functions.
Runs blocking yfinance/NSE calls in a thread pool so they don't block the event loop.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict
import pandas as pd
import logging

from data_fetcher import (
    fetch_ohlcv,
    fetch_vix_history,
    get_vix_all,
    get_india_vix,
    get_vix_prev_close,
    fetch_option_chain,
    parse_option_chain,
    calculate_pcr,
    calculate_max_pain,
    get_oi_support_resistance,
    analyze_oi_buildup,
    is_market_open,
    get_market_session,
    get_atm_strike,
    get_previous_day_ohlc,
    fetch_nse_live_indices,
    get_nse_live_price,
    fetch_fast_5min,
)

logger = logging.getLogger(__name__)

# Shared thread pool for blocking I/O (yfinance, NSE scraping)
_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="data_fetcher")


class AsyncDataFetcher:
    """Async wrapper around all data_fetcher functions."""

    def __init__(self):
        self._loop = None

    def _get_loop(self):
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.get_event_loop()

    async def _run_in_thread(self, func, *args, **kwargs):
        loop = self._get_loop()
        return await loop.run_in_executor(_executor, lambda: func(*args, **kwargs))

    # ── Price Data ────────────────────────────────────────────
    async def fetch_ohlcv(self, symbol: str, interval: str = "15m", period: str = "10d") -> pd.DataFrame:
        return await self._run_in_thread(fetch_ohlcv, symbol, interval, period)

    async def fetch_fast_5min(self, symbol: str) -> pd.DataFrame:
        return await self._run_in_thread(fetch_fast_5min, symbol)

    async def get_nse_live_price(self, symbol: str) -> dict:
        return await self._run_in_thread(get_nse_live_price, symbol)

    async def fetch_nse_live_indices(self) -> dict:
        return await self._run_in_thread(fetch_nse_live_indices)

    # ── VIX ───────────────────────────────────────────────────
    async def get_vix_all(self) -> dict:
        return await self._run_in_thread(get_vix_all)

    async def fetch_vix_history(self, period: str = "3mo") -> pd.DataFrame:
        return await self._run_in_thread(fetch_vix_history, period)

    # ── Option Chain ──────────────────────────────────────────
    async def fetch_option_chain(self, symbol: str = "NIFTY") -> Optional[dict]:
        return await self._run_in_thread(fetch_option_chain, symbol)

    async def parse_option_chain(self, raw_data: dict):
        return await self._run_in_thread(parse_option_chain, raw_data)

    async def get_previous_day_ohlc(self, symbol: str) -> dict:
        return await self._run_in_thread(get_previous_day_ohlc, symbol)

    # ── Sync helpers (no I/O, safe to call directly) ──────────
    @staticmethod
    def calculate_pcr(oc_df, expiry=None):
        return calculate_pcr(oc_df, expiry)

    @staticmethod
    def calculate_max_pain(oc_df, expiry=None):
        return calculate_max_pain(oc_df, expiry)

    @staticmethod
    def get_oi_support_resistance(oc_df, underlying, expiry=None, n=3):
        return get_oi_support_resistance(oc_df, underlying, expiry, n)

    @staticmethod
    def analyze_oi_buildup(oc_df, underlying, expiry=None):
        return analyze_oi_buildup(oc_df, underlying, expiry)

    @staticmethod
    def is_market_open():
        return is_market_open()

    @staticmethod
    def get_market_session():
        return get_market_session()

    @staticmethod
    def get_atm_strike(price, step):
        return get_atm_strike(price, step)


# Singleton
data_fetcher = AsyncDataFetcher()
