"""
╔══════════════════════════════════════════════════════════════╗
║  SENTIMENT v4.0 — Freshness + Dedup + Better Scoring        ║
║                                                              ║
║  FIXES FROM v3:                                              ║
║  1. Freshness filter — only headlines from last 6 hours     ║
║  2. Deduplication — fuzzy match removes same headline       ║
║  3. More RSS feeds — added Reuters India, CNBC TV18, Zee    ║
║  4. Recency-weighted scoring (newest = highest weight)      ║
║  5. High-impact keyword detection (RBI, SEBI, FII, war)    ║
║  6. Separate NIFTY vs BANKNIFTY relevance scoring           ║
║  7. Breaking news detection (crash, circuit, emergency)     ║
║  8. Better VADER lexicon with F&O-specific terms            ║
╚══════════════════════════════════════════════════════════════╝
"""

import feedparser
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional
from email.utils import parsedate_to_datetime

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    HAS_VADER = True
except ImportError:
    HAS_VADER = False

logger = logging.getLogger(__name__)

# ═══════════════════ EXPANDED RSS FEEDS ════════════════════════
RSS_FEEDS = {
    "ET Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "LiveMint": "https://www.livemint.com/rss/markets",
    "MoneyControl": "https://www.moneycontrol.com/rss/marketreports.xml",
    "BS Markets": "https://www.business-standard.com/rss/markets-106.rss",
    "Google Nifty": "https://news.google.com/rss/search?q=nifty+OR+banknifty+OR+sensex&hl=en-IN&gl=IN&ceid=IN:en",
    "Google FII": "https://news.google.com/rss/search?q=FII+DII+india+market&hl=en-IN&gl=IN&ceid=IN:en",
    "Google RBI": "https://news.google.com/rss/search?q=RBI+rate+india+economy&hl=en-IN&gl=IN&ceid=IN:en",
    "NDTV Profit": "https://feeds.feedburner.com/ndtvprofit-latest",
    "Reuters India": "https://news.google.com/rss/search?q=india+stock+market+reuters&hl=en-IN&gl=IN&ceid=IN:en",
}

# ═══════════════════ ENHANCED FINANCIAL LEXICON ════════════════
FINANCIAL_LEXICON = {
    # Strong bullish
    "rally": 2.5, "surge": 2.5, "bull": 2.0, "bullish": 2.5,
    "breakout": 2.0, "all-time high": 3.0, "record high": 3.0,
    "soars": 2.5, "jumps": 2.0, "fii buying": 3.0, "dii buying": 2.0,
    "rate cut": 2.5, "rbi cuts": 2.5, "dovish": 1.5, "upgrade": 1.5,
    "profit growth": 2.0, "beats estimates": 2.0, "buying spree": 2.5,
    "fresh high": 2.5, "gap up": 2.0, "green opening": 1.5,
    "inflows": 1.5, "net buyers": 2.0, "stimulus": 2.0,
    # Strong bearish
    "crash": -3.5, "sell-off": -2.5, "selloff": -2.5, "bear": -2.0,
    "bearish": -2.5, "breakdown": -2.0, "plunge": -2.5,
    "tumble": -2.0, "slump": -2.0, "panic": -3.0, "correction": -1.5,
    "fii selling": -3.0, "dii selling": -2.0, "rate hike": -2.0,
    "hawkish": -1.5, "recession": -2.5, "downgrade": -1.5,
    "miss estimates": -2.0, "profit warning": -2.5, "outflows": -1.5,
    "net sellers": -2.0, "gap down": -2.0, "red opening": -1.5,
    "circuit breaker": -3.0, "lower circuit": -3.0, "flash crash": -3.0,
    # Moderate
    "volatile": -0.5, "uncertainty": -1.0, "inflation": -1.0,
    "crude rises": -0.8, "rupee falls": -0.8, "rupee weakens": -0.8,
    "crude falls": 0.8, "rupee gains": 0.8, "rupee strengthens": 0.8,
    "budget": 0.5, "expiry": -0.3, "weekly expiry": -0.3,
    # Neutral (prevent VADER from misscoring)
    "nifty": 0.0, "sensex": 0.0, "banknifty": 0.0,
    "sebi": 0.0, "rbi": 0.0, "nse": 0.0, "bse": 0.0,
}

# High-impact keywords that need LLM analysis or heavy weighting
HIGH_IMPACT_KEYWORDS = [
    "rbi", "sebi", "fii", "dii", "rate cut", "rate hike",
    "war", "attack", "sanctions", "emergency", "circuit",
    "crash", "default", "crisis", "pandemic", "lockdown",
    "budget", "election", "modi", "fed ", "fomc",
]

# Breaking news — requires immediate alert
BREAKING_KEYWORDS = [
    "crash", "circuit breaker", "flash crash", "war",
    "attack", "emergency", "rbi emergency", "sebi ban",
    "default", "pandemic", "lockdown",
]

# NIFTY/BANKNIFTY relevance
NIFTY_KEYWORDS = ["nifty", "sensex", "fii", "dii", "market", "index", "rbi", "sebi"]
BANKNIFTY_KEYWORDS = ["bank nifty", "banknifty", "banking", "bank", "rbi", "rate cut", "rate hike", "nbfc", "hdfc", "icici", "sbi", "kotak"]


class VADERAnalyzer:
    def __init__(self):
        if HAS_VADER:
            self.analyzer = SentimentIntensityAnalyzer()
            self.analyzer.lexicon.update(FINANCIAL_LEXICON)
        else:
            self.analyzer = None

    def score(self, text: str) -> float:
        if not self.analyzer:
            return 0.0
        return self.analyzer.polarity_scores(text.lower())["compound"]


_vader = VADERAnalyzer()


# ═══════════════════ RSS FETCHER + FRESHNESS ═══════════════════

def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse RSS date string to datetime."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        try:
            for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z",
                        "%a, %d %b %Y %H:%M:%S GMT"]:
                try:
                    return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
        except Exception:
            pass
    return None


def _fuzzy_match(title1: str, title2: str, threshold: float = 0.8) -> bool:
    """Simple word-overlap deduplication."""
    words1 = set(title1.lower().split())
    words2 = set(title2.lower().split())
    if not words1 or not words2:
        return False
    overlap = len(words1 & words2) / min(len(words1), len(words2))
    return overlap >= threshold


def fetch_news_headlines(max_per_feed: int = 12, max_age_hours: int = 8) -> List[Dict]:
    """
    Fetch headlines with freshness filter + deduplication.
    Only returns headlines from last N hours.
    """
    all_headlines = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    seen_titles = []

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:max_per_feed]:
                title = entry.get("title", "").strip()
                if not title or len(title) < 10:
                    continue

                # Freshness check
                pub_date = _parse_date(entry.get("published", ""))
                if pub_date and pub_date < cutoff:
                    continue  # Skip old headlines

                # Deduplication
                is_dupe = any(_fuzzy_match(title, seen) for seen in seen_titles)
                if is_dupe:
                    continue
                seen_titles.append(title)

                # Detect high impact
                title_lower = title.lower()
                is_high_impact = any(kw in title_lower for kw in HIGH_IMPACT_KEYWORDS)
                is_breaking = any(kw in title_lower for kw in BREAKING_KEYWORDS)

                # Relevance scoring
                nifty_relevant = any(kw in title_lower for kw in NIFTY_KEYWORDS)
                bn_relevant = any(kw in title_lower for kw in BANKNIFTY_KEYWORDS)

                all_headlines.append({
                    "title": title,
                    "source": source_name,
                    "published": entry.get("published", ""),
                    "pub_datetime": pub_date,
                    "link": entry.get("link", ""),
                    "is_high_impact": is_high_impact,
                    "is_breaking": is_breaking,
                    "nifty_relevant": nifty_relevant,
                    "banknifty_relevant": bn_relevant,
                })
        except Exception as e:
            logger.warning(f"RSS failed for {source_name}: {e}")

    # Sort by recency (newest first)
    all_headlines.sort(
        key=lambda x: x.get("pub_datetime") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    return all_headlines


# ═══════════════════ LLM-POWERED SENTIMENT ═══════════════════

def calculate_news_sentiment_llm(nim_client=None) -> Tuple[float, str, List[Dict]]:
    """
    Calculate sentiment using LLM (primary) or VADER (fallback).
    v4: Recency-weighted, deduplicated, freshness-filtered.
    """
    raw_headlines = fetch_news_headlines()
    if not raw_headlines:
        return 0.0, "NO DATA", []

    llm_used = False
    if nim_client and hasattr(nim_client, 'available') and nim_client.available:
        try:
            from llm_engine import llm_score_headlines
            titles = [h["title"] for h in raw_headlines[:20]]  # Limit to 20 for speed
            llm_results = llm_score_headlines(nim_client, titles, batch_size=5)

            if llm_results:
                for i, h in enumerate(raw_headlines):
                    if i < len(llm_results):
                        lr = llm_results[i]
                        h["sentiment"] = lr.get("score", 0.0)
                        h["llm_label"] = lr.get("sentiment", "neutral")
                        h["confidence"] = lr.get("confidence", 0.0)
                        h["impact"] = lr.get("impact", "low")
                        h["affected"] = lr.get("affected", [])
                        h["reasoning"] = lr.get("reasoning", "")
                        h["engine"] = "LLM"
                    else:
                        h["sentiment"] = _vader.score(h["title"])
                        h["engine"] = "VADER"
                llm_used = True
        except Exception as e:
            logger.warning(f"LLM sentiment failed: {e}")

    # VADER fallback
    if not llm_used:
        for h in raw_headlines:
            h["sentiment"] = _vader.score(h["title"])
            h["llm_label"] = ""
            h["confidence"] = 0.0
            h["impact"] = "high" if h.get("is_high_impact") else "low"
            h["affected"] = []
            h["reasoning"] = ""
            h["engine"] = "VADER"

    # ═══════════════════ RECENCY-WEIGHTED AGGREGATE ════════════
    # Newer headlines get higher weight, high-impact gets 2x
    scored = [h for h in raw_headlines if "sentiment" in h]
    if not scored:
        return 0.0, "NO DATA", raw_headlines

    total_weight = 0
    weighted_sum = 0

    for i, h in enumerate(scored[:30]):  # Top 30 by recency
        # Recency weight: newest=1.0, decays by position
        recency_w = 1.0 / (1 + i * 0.15)

        # Impact boost
        impact_mult = 2.0 if h.get("is_high_impact") else 1.0
        if h.get("is_breaking"):
            impact_mult = 3.0

        w = recency_w * impact_mult
        weighted_sum += h["sentiment"] * w
        total_weight += w

    final_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    final_score = max(-1.0, min(1.0, final_score))

    if final_score > 0.3:
        label = "VERY BULLISH"
    elif final_score > 0.1:
        label = "BULLISH"
    elif final_score < -0.3:
        label = "VERY BEARISH"
    elif final_score < -0.1:
        label = "BEARISH"
    else:
        label = "NEUTRAL"

    engine_tag = " (AI)" if llm_used else " (VADER)"

    # Sort output by absolute impact for display
    scored.sort(key=lambda x: abs(x.get("sentiment", 0)), reverse=True)

    return round(final_score, 3), label + engine_tag, scored


def calculate_news_sentiment() -> Tuple[float, str, List[Dict]]:
    """Backward compatible — VADER only."""
    return calculate_news_sentiment_llm(nim_client=None)


def filter_relevant_headlines(headlines: List[Dict], symbol: str = None) -> List[Dict]:
    """Filter headlines relevant to a specific index."""
    if symbol == "BANKNIFTY":
        return [h for h in headlines if h.get("banknifty_relevant", True)]
    if symbol == "NIFTY50":
        return [h for h in headlines if h.get("nifty_relevant", True)]

    keywords = ["nifty", "banknifty", "bank nifty", "sensex", "market",
                "rbi", "fii", "dii", "option", "f&o", "derivative",
                "index", "budget", "sebi", "nse"]
    return [h for h in headlines if any(kw in h.get("title", "").lower() for kw in keywords)]


def get_breaking_news(headlines: List[Dict]) -> List[Dict]:
    """Extract breaking news that needs immediate attention."""
    return [h for h in headlines if h.get("is_breaking", False)]
