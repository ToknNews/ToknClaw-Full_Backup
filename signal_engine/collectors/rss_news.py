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
# MODULE: rss_news
# PURPOSE:
# - Ingest crypto-native RSS news feeds
# - Output normalized raw signals for clustering + narrative
# - Preserve raw_url for click-through intelligence
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

import feedparser
from datetime import datetime, timezone
from typing import List

from signal_engine.collectors.registry import register_collector
from signal_engine.models.signal import Signal


# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://www.theblock.co/feed",
    "https://decrypt.co/feed",
    "https://cryptoslate.com/feed/",
    "https://beincrypto.com/feed/",
    "https://u.today/rss",
    "https://coingape.com/feed/",
    "https://bitcoinmagazine.com/feed",
    "https://thedefiant.io/feed/",
    "https://cryptopotato.com/feed/",
    "https://cryptonews.com/news/feed/",
    "https://blockworks.co/feed/",
    "https://bankless.com/feed/",
    "https://protos.com/feed/",
    "https://coinbureau.com/feed/",
    "https://ledgerinsights.com/feed/",
    "https://www.ccn.com/feed/",
    "https://cryptobriefing.com/feed/"
]

# ---------------------------------------------------
# COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="rss_news",
    tags=["news", "macro", "rss"],
    priority=1,
    execution="slow"
)

def fetch_rss_signals() -> List[Signal]:
    signals: List[Signal] = []
    seen_urls = set()

    for feed in FEEDS:
        try:
            parsed = feedparser.parse(feed)

            # limit entries per feed (prevents overload)
            for entry in parsed.entries[:3]:

                title = entry.get("title", "") or ""
                link = entry.get("link", "") or ""

                # basic validation
                if not title or not link:
                    continue

                # 🔴 GLOBAL DEDUPE
                if link in seen_urls:
                    continue
                seen_urls.add(link)

                summary = ""

                if "summary" in entry:
                    summary = entry.summary
                elif "description" in entry:
                    summary = entry.description

                signals.append(
                    Signal(
                        timestamp=datetime.now(timezone.utc),
                        source="rss",
                        signal_type="news",
                        entity=None,
                        title=title[:220],
                        summary=summary[:400] if summary else "",
                        confidence=0.65,
                        raw_url=link
                    )
                )

        except Exception as e:
            print(f"[RSS NEWS] feed failed {feed} → {e}")
            continue

    print(f"[RSS NEWS] signals={len(signals)} unique_urls={len(seen_urls)}")

    return signals
