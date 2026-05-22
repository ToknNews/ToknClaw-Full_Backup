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
# MODULE: culture
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations
from typing import Any, Dict, List
from collections import Counter
import re

TOKEN_RE = re.compile(r"\b[A-Z]{2,6}\b")
MEME_TOKENS = {"DOGE", "PEPE", "PENGU", "BONK", "WIF", "FLOKI", "SHIB", "BRETT", "POPCAT"}


def _extract_token(item: Dict[str, Any]) -> str | None:
    token = item.get("token")
    if token:
        return str(token).upper()

    text = f"{item.get('title', '')} {item.get('text', '')}".upper()
    matches = TOKEN_RE.findall(text)
    for m in matches:
        if m not in {"HTTP", "HTTPS", "USD", "THE", "AND", "WITH"}:
            return m
    return None


def build_culture_vertical(
    reddit_items: List[Dict[str, Any]] | None = None,
    x_items: List[Dict[str, Any]] | None = None,
    dex_items: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    reddit_items = reddit_items or []
    x_items = x_items or []
    dex_items = dex_items or []

    reddit_counter = Counter()
    x_counter = Counter()
    notes: List[str] = []

    for item in reddit_items:
        token = _extract_token(item)
        if token:
            reddit_counter[token] += int(item.get("mentions", 1) or 1)

    for item in x_items:
        token = _extract_token(item)
        if token:
            x_counter[token] += int(item.get("mentions", 1) or 1)

    reddit_top_tokens = [token for token, _ in reddit_counter.most_common(5)]
    x_trending = [token for token, _ in x_counter.most_common(5)]

    memecoin_rotation = False

    if any(token in MEME_TOKENS for token in reddit_top_tokens + x_trending):
        memecoin_rotation = True

    for item in dex_items:
        token = _extract_token(item)
        if token in MEME_TOKENS:
            memecoin_rotation = True
            break

    if reddit_top_tokens:
        notes.append(f"Reddit chatter active in {', '.join(reddit_top_tokens[:3])}.")
    if x_trending:
        notes.append(f"X narrative active in {', '.join(x_trending[:3])}.")
    if memecoin_rotation:
        notes.append("Memecoin rotation detected.")

    if memecoin_rotation and (reddit_top_tokens or x_trending):
        retail_sentiment = "risk_on"
    elif reddit_top_tokens or x_trending:
        retail_sentiment = "active"
    else:
        retail_sentiment = "unknown"

    return {
        "reddit_top_tokens": reddit_top_tokens,
        "x_trending": x_trending,
        "memecoin_rotation": memecoin_rotation,
        "retail_sentiment": retail_sentiment,
        "notes": notes,
        "raw_counts": {
            "reddit_items": len(reddit_items),
            "x_items": len(x_items),
            "dex_items": len(dex_items),
        },
    }
