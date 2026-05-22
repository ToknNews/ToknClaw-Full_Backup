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
# MODULE: reddit_sentiment
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================

import requests
import re
from datetime import datetime

SUBREDDITS = [
    "CryptoCurrency",
    "ethtrader",
    "bitcoin",
    "solana",
    "wallstreetbetscrypto",
    "memecoins",
    "cryptomoonshots"
]

TOKEN_REGEX = re.compile(r"\b[A-Z]{2,6}\b")

HEADERS = {
    "User-Agent": "ToknClawRetailScanner/1.0"
}


def fetch_reddit_signals():

    signals = []
    token_counts = {}

    for sub in SUBREDDITS:

        url = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"

        try:
            r = requests.get(url, headers=HEADERS, timeout=10)

            if r.status_code != 200:
                continue

            data = r.json()

        except Exception:
            continue

        posts = data.get("data", {}).get("children", [])

        for p in posts:

            title = p["data"].get("title", "")

            tokens = TOKEN_REGEX.findall(title)

            for t in tokens:

                token_counts[t] = token_counts.get(t, 0) + 1

    if not token_counts:
        return []

    top_tokens = sorted(
        token_counts.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]

    for token, count in top_tokens:

        signals.append({
            "source": "culture",
            "signal_type": "reddit_narrative",
            "entity": token,
            "title": f"{token} gaining Reddit narrative momentum",
            "summary": f"{token} mentioned {count} times across major crypto subreddits",
            "confidence": 0.6,
            "sentiment_score": None,
            "raw_url": None,
            "timestamp": datetime.utcnow().isoformat()
        })

    return signals
