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
# MODULE: cryptopanic
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================

import os
import re
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from models.signal import Signal

load_dotenv()

CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "").strip()

CRYPTOPANIC_V2_URL = "https://cryptopanic.com/api/developer/v2/posts/"

LAST_CALL = 0
MIN_INTERVAL = 120


TOKEN_MAP = {
    "bitcoin": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "eth": "ETH",
    "solana": "SOL",
    "sol": "SOL",
    "xrp": "XRP",
    "ripple": "XRP",
    "ton": "TON",
    "toncoin": "TON",
    "doge": "DOGE",
    "dogecoin": "DOGE",
    "cardano": "ADA",
    "ada": "ADA",
    "bnb": "BNB",
    "binance": "BNB"
}


# ---------------------------------------------------------
# ENTITY DETECTION
# ---------------------------------------------------------

def detect_entity(text):

    if not text:
        return None

    text = text.lower()

    for keyword, token in TOKEN_MAP.items():

        if re.search(r"\b" + re.escape(keyword) + r"\b", text):

            return token

    return None


# ---------------------------------------------------------
# SENTIMENT
# ---------------------------------------------------------

def compute_sentiment(post):

    votes = post.get("votes") or {}

    bullish = votes.get("positive", 0)
    bearish = votes.get("negative", 0)

    total = bullish + bearish

    if total == 0:
        return None

    return (bullish - bearish) / total


# ---------------------------------------------------------
# ENTITY EXTRACTION
# ---------------------------------------------------------

def extract_entity(post):

    currencies = post.get("currencies") or []

    if currencies:

        first = currencies[0]

        if isinstance(first, dict):

            return first.get("code")

        if isinstance(first, str):

            return first

    return None


# ---------------------------------------------------------
# PAYLOAD PARSER
# ---------------------------------------------------------

def extract_results(payload):

    if isinstance(payload, dict):

        if isinstance(payload.get("results"), list):

            return payload["results"]

        if isinstance(payload.get("data"), list):

            return payload["data"]

        if isinstance(payload.get("posts"), list):

            return payload["posts"]

    return []


# ---------------------------------------------------------
# MAIN COLLECTOR
# ---------------------------------------------------------

def fetch_cryptopanic_signals():

    global LAST_CALL

    now = time.time()

    # -----------------------------------------
    # RATE LIMIT PROTECTION
    # -----------------------------------------

    if now - LAST_CALL < MIN_INTERVAL:

        print("[CRYPTOPANIC] skipped (rate limited)")

        return []

    LAST_CALL = now

    if not CRYPTOPANIC_API_KEY:

        print("[CRYPTOPANIC] missing API key")

        return []

    params = {
        "auth_token": CRYPTOPANIC_API_KEY,
        "kind": "news",
        "filter": "hot",
        "currencies": "BTC,ETH,SOL,TON",
        "regions": "en"
    }

    headers = {
        "Accept": "application/json",
        "User-Agent": "ToknClaw-SignalEngine/1.0"
    }

    try:

        response = requests.get(
            CRYPTOPANIC_V2_URL,
            params=params,
            headers=headers,
            timeout=15
        )

    except Exception as e:

        print("[CRYPTOPANIC] request failed:", e)

        return []

    # -----------------------------------------
    # HANDLE RATE LIMIT
    # -----------------------------------------

    if response.status_code == 429:

        print("[CRYPTOPANIC] rate limit hit")

        return []

    if response.status_code != 200:

        print(f"[CRYPTOPANIC] HTTP error: {response.status_code}")

        return []

    try:

        payload = response.json()

    except Exception:

        print("[CRYPTOPANIC] invalid JSON")

        return []

    posts = extract_results(payload)

    signals = []

    for post in posts[:10]:

        title = post.get("title") or ""

        if not title:

            continue

        description = (
            post.get("description")
            or post.get("body")
            or ""
        )

        url = post.get("url") or post.get("canonical_url")

        entity = extract_entity(post)

        if not entity:

            entity = detect_entity(title + " " + description)

        sentiment = compute_sentiment(post)

        confidence = 0.82

        if entity:

            confidence = 0.88

        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="cryptopanic",
                signal_type="news",
                entity=entity,
                title=title,
                summary=description,
                confidence=confidence,
                sentiment_score=sentiment,
                raw_url=url
            )
        )

    return signals
