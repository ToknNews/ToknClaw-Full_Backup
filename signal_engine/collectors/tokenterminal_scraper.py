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
# MODULE: tokenterminal_scraper
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


import requests
from bs4 import BeautifulSoup
from datetime import datetime
from models.signal import Signal

TOKENTERMINAL_URL = "https://tokenterminal.com/terminal/projects"

HEADERS = {
    "User-Agent": "ToknClaw-SignalEngine/1.0"
}


def _parse_value(text):

    if not text:
        return None

    text = text.replace(",", "").strip()

    try:
        if text.endswith("B"):
            return float(text[:-1]) * 1_000_000_000

        if text.endswith("M"):
            return float(text[:-1]) * 1_000_000

        if text.endswith("K"):
            return float(text[:-1]) * 1_000

        return float(text)

    except Exception:
        return None

def fetch_tokenterminal_scraped_signals():

    try:
        r = requests.get(TOKENTERMINAL_URL, headers=HEADERS, timeout=20)
    except Exception as e:
        print("[TOKENTERMINAL] request failed:", e)
        return []

    if r.status_code != 200:
        print("[TOKENTERMINAL] HTTP error:", r.status_code)
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    rows = soup.find_all("tr")

    signals = []

    for row in rows[:30]:

        cols = row.find_all("td")

        if len(cols) < 4:
            continue

        protocol = cols[0].text.strip()
        revenue = cols[2].text.strip()

        value_usd = _parse_value(revenue)

        if not protocol:
            continue

        title = f"{protocol} protocol revenue signal"

        if revenue:
            title = f"{protocol} revenue signal: {revenue}"

        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="tokenterminal",
                signal_type="protocol_revenue",
                entity=protocol.upper(),
                title=title,
                summary=f"{protocol} protocol revenue activity detected",
                confidence=0.86,
                sentiment_score=None,
                raw_url=f"https://tokenterminal.com/terminal/projects/{protocol.lower()}"
            )
        )

    return signals
