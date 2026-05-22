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
# MODULE: defillama_metrics
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


import requests
from datetime import datetime
from models.signal import Signal

DEFILLAMA_PROTOCOL_URL = "https://api.llama.fi/protocols"

TVL_SPIKE_THRESHOLD = 0.15
MAX_PROTOCOLS = 25


def _infer_signal_type(change_pct):

    if change_pct >= 0.25:
        return "protocol_tvl_spike"

    if change_pct >= 0.10:
        return "protocol_tvl_growth"

    if change_pct <= -0.20:
        return "protocol_tvl_drop"

    return "protocol_tvl"


def _confidence(change_pct):

    base = 0.84

    if abs(change_pct) > 0.30:
        base = 0.90
    elif abs(change_pct) > 0.20:
        base = 0.88
    elif abs(change_pct) > 0.10:
        base = 0.86

    return min(base, 0.92)


def _protocol_url(slug):

    if not slug:
        return "https://defillama.com"

    return f"https://defillama.com/protocol/{slug}"


def fetch_defillama_signals():

    try:

        r = requests.get(
            DEFILLAMA_PROTOCOL_URL,
            timeout=20,
            headers={"User-Agent": "ToknClaw/1.0"}
        )

        if r.status_code != 200:
            print("[DEFILLAMA] HTTP error:", r.status_code)
            return []

        data = r.json()

    except Exception as e:
        print("[DEFILLAMA] request failed:", e)
        return []

    if not isinstance(data, list):
        return []

    signals = []

    for protocol in data[:MAX_PROTOCOLS]:

        name = protocol.get("name")
        slug = protocol.get("slug")

        if not name:
            continue

        tvl = protocol.get("tvl")
        change_24h = protocol.get("change_1d")

        if change_24h is None:
            continue

        change_pct = float(change_24h) / 100.0

        signal_type = _infer_signal_type(change_pct)

        title = f"{name} TVL at about ${tvl:,.0f}" if tvl else f"{name} TVL update"

        summary = f"{name} showing {change_24h:.2f}% TVL change in the last 24 hours"

        signal = Signal(
            timestamp=datetime.utcnow(),
            source="defillama",
            signal_type=signal_type,
            entity=name.upper(),
            title=title,
            summary=summary,
            confidence=_confidence(change_pct),
            sentiment_score=None,
            raw_url=_protocol_url(slug)
        )

        try:
            signal.value_usd = float(tvl) if tvl else None
        except Exception:
            pass

        try:
            signal.change_pct = change_pct
        except Exception:
            pass

        signals.append(signal)

    return signals
