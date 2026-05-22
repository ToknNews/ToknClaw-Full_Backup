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
# MODULE: dlnews_scraper
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from models.signal import Signal

DLNEWS_URL = "https://www.dlnews.com"
DLNEWS_NEWS_URL = "https://www.dlnews.com/articles"

TOKEN_MAP = {
    "bitcoin": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "eth": "ETH",
    "solana": "SOL",
    "sol": "SOL",
    "cardano": "ADA",
    "ada": "ADA",
    "xrp": "XRP",
    "ripple": "XRP",
    "dogecoin": "DOGE",
    "doge": "DOGE",
    "bnb": "BNB",
    "avalanche": "AVAX",
    "avax": "AVAX",
    "arbitrum": "ARB",
    "arb": "ARB",
    "optimism": "OP",
    "op": "OP",
    "aave": "AAVE",
    "uniswap": "UNI",
    "pepe": "PEPE",
    "pengu": "PENGU",
}

HEADERS = {
    "User-Agent": "ToknClaw-ResearchBot/1.0",
    "Accept-Language": "en-US,en;q=0.9",
}


def _detect_entity(text):
    if not text:
        return None

    text_lower = text.lower()

    for keyword, token in TOKEN_MAP.items():
        if re.search(r"\b" + re.escape(keyword) + r"\b", text_lower):
            return token

    return None


def fetch_dlnews_signals():
    try:
        response = requests.get(
            DLNEWS_NEWS_URL,
            headers=HEADERS,
            timeout=15
        )
    except Exception as e:
        print(f"[DLNEWS] request failed: {e}")
        return []

    if response.status_code != 200:
        print(f"[DLNEWS] HTTP error: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "lxml")
    links = soup.find_all("a", href=True)

    seen = set()
    signals = []

    for link in links:
        href = link.get("href") or ""
        title = " ".join(link.stripped_strings).strip()

        if not title or len(title) < 25:
            continue

        if "/news/" not in href:
            continue

        if href.startswith("/"):
            url = DLNEWS_URL + href
        elif href.startswith("http"):
            url = href
        else:
            continue

        if url in seen:
            continue
        seen.add(url)

        entity = _detect_entity(title)

        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="dlnews",
                signal_type="news",
                entity=entity,
                title=title,
                summary=title,
                confidence=0.83 if entity else 0.76,
                sentiment_score=None,
                raw_url=url
            )
        )

        if len(signals) >= 10:
            break

    return signals
