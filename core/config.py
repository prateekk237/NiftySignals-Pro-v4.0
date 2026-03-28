"""
Core configuration using Pydantic BaseSettings.
Wraps all constants from the original config.py and adds env-var support.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os

# ── Import ALL original constants (no logic changes) ──────────────
from config import (
    NIFTY_LOT_SIZE, BANKNIFTY_LOT_SIZE,
    TICKERS, GLOBAL_SIGNAL_MARKETS, CORRELATION_DIRECTION,
    VIX_ZONES, VIX_LOW, VIX_NORMAL_LOW, VIX_NORMAL_HIGH, VIX_HIGH, VIX_EXTREME,
    VIX_SPIKE_PCT, VIX_INTRADAY_SPIKE,
    BTST_WEIGHTS, GAP_STRONG_CONFIDENCE, GAP_MODERATE_CONFIDENCE,
    ALERT_CONFIG, BREAKING_NEWS_KEYWORDS,
    NSE_BASE, NSE_OPTION_CHAIN_URL, NSE_INDEX_URL, NSE_FII_DII_URL, NSE_HEADERS,
    ST_FAST, ST_MEDIUM, ST_SLOW,
    RSI_FAST, RSI_STANDARD, RSI_OVERBOUGHT, RSI_OVERSOLD,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    EMA_SCALP, EMA_INTRADAY, EMA_SWING, EMA_POSITIONAL,
    BB_LENGTH, BB_STD, ADX_LENGTH, ADX_STRONG_TREND, ADX_WEAK_TREND,
    STRATEGY_WEIGHTS, STRONG_BUY_THRESHOLD, BUY_THRESHOLD,
    NEUTRAL_LOW, STRONG_SELL_THRESHOLD,
    MAX_RISK_PER_TRADE_PCT, DEFAULT_CAPITAL, MAX_DAILY_LOSS_PCT,
    RISK_REWARD_MIN, SL_OPTION_BUY_PCT, SL_OPTION_SELL_MULT, SL_ATR_MULTIPLIER,
    PCR_EXTREME_BULLISH, PCR_BULLISH, PCR_BEARISH, PCR_EXTREME_BEARISH,
    RSS_FEEDS, TIMEFRAMES,
    STRIKE_STEP_NIFTY, STRIKE_STEP_BANKNIFTY,
    PREMIUM_TARGET_RANGE,
)


class Settings(BaseSettings):
    """Environment-based settings for the FastAPI backend."""

    # ── Server ────────────────────────────────────────────────
    port: int = Field(default=8000, alias="PORT")
    cors_origins: str = Field(
        default="http://localhost:3000,https://localhost:3000",
        alias="CORS_ORIGINS",
    )

    # ── NVIDIA NIM ────────────────────────────────────────────
    nvidia_api_key: str = Field(default="", alias="NVIDIA_API_KEY")

    # ── Database ──────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite:///./btst_history.db",
        alias="DATABASE_URL",
    )

    # ── Redis (empty = use in-memory dict) ────────────────────
    redis_url: str = Field(default="", alias="REDIS_URL")

    # ── Feature Flags ─────────────────────────────────────────
    enable_llm: bool = Field(default=True, alias="ENABLE_LLM")
    enable_sentiment: bool = Field(default=True, alias="ENABLE_SENTIMENT")
    enable_option_chain: bool = Field(default=True, alias="ENABLE_OPTION_CHAIN")

    # ── Logging ───────────────────────────────────────────────
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Singleton
settings = Settings()
