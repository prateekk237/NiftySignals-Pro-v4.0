"""
SentimentService — wraps original sentiment.py.
LLM-first with VADER fallback, runs in thread pool.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple, List

from sentiment import (
    calculate_news_sentiment_llm,
    calculate_news_sentiment,
    filter_relevant_headlines,
)

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sentiment")


class SentimentService:
    """News sentiment analysis with LLM + VADER fallback."""

    async def calculate_sentiment(self, nim_client=None) -> Tuple[float, str, List]:
        """
        Get news sentiment. Uses LLM if client provided, VADER fallback otherwise.
        Returns (score, label, headlines_list).
        """
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                _executor,
                calculate_news_sentiment_llm,
                nim_client,
            )
            return result
        except Exception as e:
            logger.warning(f"LLM sentiment failed, using VADER: {e}")
            try:
                result = await loop.run_in_executor(
                    _executor,
                    calculate_news_sentiment_llm,
                    None,  # None client triggers VADER fallback internally
                )
                return result
            except Exception as e2:
                logger.error(f"All sentiment failed: {e2}")
                return 0.0, "N/A", []

    @staticmethod
    def filter_relevant(headlines: list) -> list:
        return filter_relevant_headlines(headlines)


# Singleton
sentiment_service = SentimentService()
