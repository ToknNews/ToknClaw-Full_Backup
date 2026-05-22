#!/usr/bin/env python3

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
# MODULE: ranker
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
████████╗ ██████╗ ██╗  ██╗███╗   ██╗
╚══██╔══╝██╔═══██╗██║ ██╔╝████╗  ██║
   ██║   ██║   ██║█████╔╝ ██╔██╗ ██║
   ██║   ██║   ██║██╔═██╗ ██║╚██╗██║
   ██║   ╚██████╔╝██║  ██╗██║ ╚████║
   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝

TOKNCLAW SIGNAL ENGINE
Signal Ranking Engine

Purpose
-------
Score and rank raw signals collected from the ToknClaw collector layer.

The ranker prioritizes signals based on:

• source credibility
• entity importance
• signal type
• sentiment magnitude
• signal freshness

The output score determines which signals survive
diversification and drive cluster/narrative generation.

Design Goals
------------

• deterministic
• fast (runs every snapshot cycle)
• tolerant of both object and dict signals
• easily extendable for quant signals later

Author: TOKN Systems
"""

from datetime import datetime, timezone


# ---------------------------------------------------
# ENTITY IMPORTANCE
# ---------------------------------------------------

ENTITY_WEIGHTS = {
    "BTC": 1.0,
    "ETH": 0.95,
    "SOL": 0.9,
    "XRP": 0.85,
    "TON": 0.8,
    "STABLECOINS": 0.8,
    "DEFI": 0.75,
}


# ---------------------------------------------------
# SOURCE CREDIBILITY
# ---------------------------------------------------

SOURCE_WEIGHTS = {

    # institutional / analytics
    "tokenterminal": 1.0,
    "defillama": 0.95,

    # macro
    "fred": 0.95,

    # news aggregators
    "cryptopanic": 0.85,

    # rss (generic)
    "rss": 0.7,

    # fallback
    "unknown": 0.5
}


# ---------------------------------------------------
# SIGNAL TYPE IMPORTANCE
# ---------------------------------------------------

TYPE_WEIGHTS = {

    "macro_indicator": 0.9,
    "protocol_revenue": 0.9,
    "protocol_tvl": 0.85,

    "macro_news": 0.75,
    "policy_news": 0.75,
    "defi_news": 0.7,
    "news_theme": 0.6,

    "retail_sentiment": 0.6
}


# ---------------------------------------------------
# SIGNAL ACCESSOR
# ---------------------------------------------------

def _get(signal, key, default=None):
    """
    Supports both object signals and dict signals.
    """

    if isinstance(signal, dict):
        return signal.get(key, default)

    return getattr(signal, key, default)


# ---------------------------------------------------
# MAIN SCORING FUNCTION
# ---------------------------------------------------

def compute_score(signal):

    score = 0.0

    source = _get(signal, "source", "unknown")
    entity = _get(signal, "entity")
    signal_type = _get(signal, "signal_type")
    sentiment = _get(signal, "sentiment_score")
    timestamp = _get(signal, "timestamp")

    # ---------------------------------------------------
    # SOURCE CREDIBILITY
    # ---------------------------------------------------

    score += SOURCE_WEIGHTS.get(source.split(":")[0], 0.5)

    # ---------------------------------------------------
    # ENTITY IMPORTANCE
    # ---------------------------------------------------

    if entity:
        score += ENTITY_WEIGHTS.get(entity, 0.5)

    # ---------------------------------------------------
    # SIGNAL TYPE
    # ---------------------------------------------------

    if signal_type:
        score += TYPE_WEIGHTS.get(signal_type, 0.5)

    # ---------------------------------------------------
    # SENTIMENT
    # ---------------------------------------------------

    if sentiment is not None:
        score += abs(sentiment) * 0.5

    # ---------------------------------------------------
    # FRESHNESS
    # ---------------------------------------------------

    if timestamp:

        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except Exception:
                timestamp = None

        if isinstance(timestamp, datetime):

            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            age_minutes = (datetime.now(timezone.utc) - timestamp).total_seconds() / 60

            freshness = max(0, 1 - (age_minutes / 180))

            score += freshness

    return round(score, 4)
