#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — MARKET INTELLIGENCE ENGINE
# ============================================================
#
# ████████╗ ██████╗ ██╗  ██╗███╗   ██╗ ██████╗██╗      █████╗ ██╗    ██╗
# ╚══██╔══╝██╔═══██╗██║ ██╔╝████╗  ██║██╔════╝██║     ██╔══██╗██║    ██║
#    ██║   ██║   ██║█████╔╝ ██╔██╗ ██║██║     ██║     ███████║██║ █╗ ██║
#    ██║   ██║   ██║██╔═██╗ ██║╚██╗██║██║     ██║     ██╔══██║██║███╗██║
#    ██║   ╚██████╔╝██║  ██╗██║ ╚████║╚██████╗███████╗██║  ██║╚███╔███╔╝
#    ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
#
# SYSTEM: ToknClaw Intelligence Layer
# MODULE: rss_global_news
# PURPOSE:
# - MAXIMUM coverage RSS ingestion layer
# - Crypto + Macro + Policy + Commodities + Central Banks
# - Structured output for clustering + orb system
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple
import html
import re

import feedparser

from signal_engine.collectors.registry import register_collector


# ---------------------------------------------------
# MAXIMUM SOURCE COVERAGE
# ---------------------------------------------------

RSS_FEEDS: List[Tuple[str, str]] = [

    # --- Crypto Core ---
    ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("cointelegraph", "https://cointelegraph.com/rss"),
    ("decrypt", "https://decrypt.co/feed"),
    ("cryptoslate", "https://cryptoslate.com/feed/"),
    ("blockworks", "https://blockworks.co/feed"),
    ("theblock", "https://www.theblock.co/feed"),
    ("beincrypto", "https://beincrypto.com/feed/"),
    ("utoday", "https://u.today/rss"),
    ("coingape", "https://coingape.com/feed/"),
    ("bitcoinmagazine", "https://bitcoinmagazine.com/feed"),
    ("thedefiant", "https://thedefiant.io/feed/"),
    ("cryptopotato", "https://cryptopotato.com/feed/"),
    ("cryptonews", "https://cryptonews.com/news/feed/"),
    ("protos", "https://protos.com/feed/"),
    ("coinbureau", "https://coinbureau.com/feed/"),
    ("ledgerinsights", "https://ledgerinsights.com/feed/"),
    ("ccn", "https://www.ccn.com/feed/"),
    ("cryptobriefing", "https://cryptobriefing.com/feed/"),

    # --- Macro / Policy ---
    ("reuters_markets", "https://feeds.reuters.com/reuters/businessNews"),
    ("reuters_world", "https://feeds.reuters.com/Reuters/worldNews"),
    ("sec_press", "https://www.sec.gov/news/pressreleases.rss"),
    ("federal_reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("ecb", "https://www.ecb.europa.eu/rss/press.html"),
    ("imf", "https://www.imf.org/en/News/RSS"),
    ("worldbank", "https://www.worldbank.org/en/news/all/rss"),

    # --- Markets / Commodities ---
    ("yahoo_finance", "https://finance.yahoo.com/news/rssindex"),
    ("marketwatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("cnbc_markets", "https://www.cnbc.com/id/20409666/device/rss/rss.html"),
    ("bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
]

MAX_ITEMS_PER_FEED = 3
DEFAULT_CONFIDENCE = 0.68

ENTITY_PATTERNS: List[Tuple[str, str]] = [
    (r"\bbitcoin\b|\bbtc\b", "BTC"),
    (r"\bethereum\b|\beth\b", "ETH"),
    (r"\bsolana\b|\bsol\b", "SOL"),
    (r"\bxrp\b", "XRP"),
    (r"\bgold\b", "GOLD"),
    (r"\boil\b", "OIL"),
    (r"\bdollar\b|\busd\b", "USD"),
    (r"\bfed\b|\bfederal reserve\b", "FED"),
    (r"\bsec\b", "SEC"),
    (r"\betf\b", "ETF"),
    (r"\binflation\b|\bcpi\b", "INFLATION"),
]

NOISE_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def _clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = NOISE_RE.sub(" ", text)
    text = SPACE_RE.sub(" ", text).strip()
    return text


def _parse_timestamp(entry: Any) -> str:
    for key in ("published", "updated"):
        raw = getattr(entry, key, None) or entry.get(key)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except:
                pass

    return datetime.now(timezone.utc).isoformat()


def _extract_entity(title: str, summary: str) -> str:
    blob = f"{title} {summary}".lower()

    for pattern, entity in ENTITY_PATTERNS:
        if re.search(pattern, blob):
            return entity

    return "NEWS"


def _classify_signal_type(title: str, summary: str) -> str:
    blob = f"{title} {summary}".lower()

    if any(x in blob for x in ["fed", "inflation", "cpi", "yield"]):
        return "macro_news"

    if any(x in blob for x in ["sec", "regulation", "etf", "policy"]):
        return "policy_news"

    if any(x in blob for x in ["defi", "protocol", "liquidity"]):
        return "defi_news"

    return "news_theme"


# ---------------------------------------------------
# COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="rss_global_news",
    tags=["news", "macro", "policy", "markets"],
    priority=2,
    execution="slow"
)
def fetch_rss_news_signals() -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    seen_urls = set()

    for source, url in RSS_FEEDS:
        try:
            parsed = feedparser.parse(url)

            for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:

                title = _clean_text(entry.get("title"))
                link = _clean_text(entry.get("link"))

                if not title or not link:
                    continue

                if link in seen_urls:
                    continue
                seen_urls.add(link)

                summary = _clean_text(entry.get("summary") or entry.get("description"))

                entity = _extract_entity(title, summary)
                signal_type = _classify_signal_type(title, summary)

                signals.append({
                    "timestamp": _parse_timestamp(entry),
                    "source": f"rss:{source}",
                    "signal_type": signal_type,
                    "entity": entity,
                    "title": title[:220],
                    "summary": summary[:400],
                    "confidence": DEFAULT_CONFIDENCE,
                    "sentiment_score": None,
                    "raw_url": link,
                })

        except Exception as e:
            print(f"[RSS GLOBAL] failed {source} → {e}")
            continue

    print(f"[RSS GLOBAL] signals={len(signals)} unique={len(seen_urls)}")

    return signals
