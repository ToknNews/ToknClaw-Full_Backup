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
# MODULE: solana_pumpfun_leaderboard
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
Solana Pump.fun Leaderboard Engine

Purpose
-------
Build a ranked leaderboard of recently active Solana memecoins using
existing ToknClaw signal lake data.

Feeds
-----
• trading bot momentum watchlists
• ToknNews meme leaderboard segments
• Bitsy funny-name commentary
• narrative enrichment
• OpenClaw strategy agents
• social / article angle generation

Scoring Inputs
--------------
• Pump.fun launches
• Pump.fun activity
• Jupiter swap flow
• Raydium pool initialization
• liquidity events
• velocity signals
• funny-name candidates

Design Notes
------------
• derived-intelligence collector
• reads the signal lake only
• no direct Solana RPC calls
• OpenClaw agents should tune:
  /opt/toknclaw/config/solana_pumpfun_leaderboard.json

Primary Output
--------------
Signals such as:
• solana_memecoin_trending
• solana_memecoin_velocity
• solana_memecoin_leaderboard
• solana_memecoin_of_the_day
• solana_bitsy_watchlist
• solana_name_theme_summary

Author: TOKN Systems
"""

from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any, Dict, List, Tuple

from signal_engine.collectors.registry import register_collector
from models.signal import Signal
from runtime_config import load_config
from signal_lake import load_signal_lake


CONFIG_FILE = "solana_pumpfun_leaderboard.json"


DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "lookback_signal_count": 3000,
    "max_tokens_to_score": 200,
    "top_n_tokens": 12,
    "max_signals_per_run": 40,
    "min_score_to_emit": 2.0,
    "emit_memecoin_of_the_day": True,
    "emit_bitsy_watchlist": True,
    "emit_name_theme_summary": True,
    "funny_name_bonus": 1.25,
    "weights": {
        "solana_pumpfun_launch": 3.0,
        "solana_pumpfun_activity": 1.0,
        "solana_jupiter_swap": 1.1,
        "solana_raydium_pool_init": 2.2,
        "solana_liquidity_event": 1.6,
        "solana_volume_velocity": 2.5,
        "solana_funny_name_candidate": 1.0,
        "solana_token_name_theme": 0.8,
        "solana_liquidity_depth": 0.6,
    },
    "theme_keywords": {
        "ai": ["ai", "agent", "gpt", "bot", "neural", "brain", "quant"],
        "dog": ["dog", "inu", "shib", "bonk", "pug", "woof"],
        "cat": ["cat", "kitty", "meow"],
        "frog": ["pepe", "frog", "ribbit"],
        "politics": ["trump", "maga", "elon", "biden", "rfk", "vote"],
        "money": ["cash", "moon", "lambo", "rich", "bank", "pump"],
        "absurd": ["butt", "fart", "toilet", "grandma", "hamster", "chad"],
    },
}


# ---------------------------------------------------
# LOGGING
# ---------------------------------------------------

def info_log(message: str) -> None:
    print(f"[SOLANA LEADERBOARD] {message}")


def debug_log(message: str) -> None:
    print(f"[SOLANA LEADERBOARD] {message}")


# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

def load_leaderboard_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)

    if not isinstance(cfg, dict):
        return dict(DEFAULT_CONFIG)

    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)

    merged_weights = dict(DEFAULT_CONFIG.get("weights", {}))
    if isinstance(cfg.get("weights"), dict):
        merged_weights.update(cfg["weights"])
    merged["weights"] = merged_weights

    merged_themes = dict(DEFAULT_CONFIG.get("theme_keywords", {}))
    if isinstance(cfg.get("theme_keywords"), dict):
        merged_themes.update(cfg["theme_keywords"])
    merged["theme_keywords"] = merged_themes

    return merged


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(UTC)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def object_signals_only(rows: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for row in rows or []:
        if isinstance(row, dict):
            out.append(row)

    return out


def is_probable_token(entity: str) -> bool:
    entity = normalize_text(entity)

    if not entity:
        return False

    if entity in {
        "SOLANA",
        "PUMPFUN",
        "PUMPFUN_ACTIVITY",
        "SOLANA_ALPHA",
        "SOLANA_MEME",
    }:
        return False

    if "/" in entity:
        return False

    return len(entity) >= 20


def extract_entity_token(row: Dict[str, Any]) -> str | None:
    entity = normalize_text(row.get("entity"))

    if is_probable_token(entity):
        return entity

    summary = normalize_text(row.get("summary"))
    title = normalize_text(row.get("title"))

    text = f"{entity} {title} {summary}"

    for part in text.replace(",", " ").split():
        cleaned = part.strip()
        if is_probable_token(cleaned):
            return cleaned

    return None


def infer_name_from_row(row: Dict[str, Any]) -> str:
    summary = normalize_text(row.get("summary"))
    title = normalize_text(row.get("title"))

    # crude fallback for now; later metadata resolver can enrich this
    for text in [summary, title]:
        if ":" in text:
            tail = text.split(":", 1)[-1].strip()
            if tail:
                return tail[:80]

    entity = normalize_text(row.get("entity"))
    return entity


def score_decay(index_from_end: int) -> float:
    # newer rows score slightly higher
    return max(0.65, 1.0 - (index_from_end * 0.0025))


def top_items(counter: Counter, limit: int) -> List[Tuple[str, int]]:
    return sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:limit]


# ---------------------------------------------------
# THEME CLASSIFICATION
# ---------------------------------------------------

def classify_token_themes(
    token_name: str,
    token_symbol: str,
    cfg: Dict[str, Any],
) -> List[str]:
    text = f"{token_name} {token_symbol}".lower().strip()
    themes: List[str] = []

    if not text:
        return themes

    for theme, keywords in cfg.get("theme_keywords", {}).items():
        if not isinstance(keywords, list):
            continue
        if any(str(keyword).lower() in text for keyword in keywords):
            themes.append(str(theme))

    return themes


# ---------------------------------------------------
# LAKE SCAN
# ---------------------------------------------------

def build_token_stats(
    rows: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    weights = cfg.get("weights", {})

    token_stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "token": "",
            "score": 0.0,
            "signal_count": 0,
            "types": Counter(),
            "sources": Counter(),
            "funny_hits": 0,
            "names": Counter(),
            "symbols": Counter(),
            "themes": Counter(),
            "sample_titles": [],
            "sample_summaries": [],
            "has_launch": False,
            "has_raydium": False,
            "has_velocity": False,
            "has_liquidity": False,
            "latest_signal_type": "",
        }
    )

    recent_rows = rows[-int(cfg.get("lookback_signal_count", 3000)):]
    indexed_rows = list(enumerate(recent_rows))

    for idx, row in indexed_rows:
        signal_type = normalize_text(row.get("signal_type"))
        if not signal_type:
            continue

        token = extract_entity_token(row)
        if not token:
            continue

        stat = token_stats[token]
        stat["token"] = token
        stat["signal_count"] += 1
        stat["types"][signal_type] += 1
        stat["sources"][normalize_text(row.get("source"))] += 1
        stat["latest_signal_type"] = signal_type

        recency_multiplier = score_decay(len(recent_rows) - idx)
        base_weight = safe_float(weights.get(signal_type, 0.0), 0.0)
        stat["score"] += base_weight * recency_multiplier

        title = normalize_text(row.get("title"))
        summary = normalize_text(row.get("summary"))

        if title and len(stat["sample_titles"]) < 4:
            stat["sample_titles"].append(title)

        if summary and len(stat["sample_summaries"]) < 4:
            stat["sample_summaries"].append(summary)

        if signal_type == "solana_pumpfun_launch":
            stat["has_launch"] = True

        if signal_type == "solana_raydium_pool_init":
            stat["has_raydium"] = True

        if signal_type == "solana_volume_velocity":
            stat["has_velocity"] = True

        if signal_type in {"solana_liquidity_event", "solana_liquidity_depth"}:
            stat["has_liquidity"] = True

        if signal_type == "solana_funny_name_candidate":
            stat["funny_hits"] += 1
            stat["score"] += safe_float(cfg.get("funny_name_bonus", 1.25), 1.25)

        if signal_type == "solana_token_name_detected":
            inferred_name = infer_name_from_row(row)
            if inferred_name:
                stat["names"][inferred_name] += 1

        if signal_type == "solana_token_symbol_detected":
            inferred_symbol = infer_name_from_row(row)
            if inferred_symbol:
                stat["symbols"][inferred_symbol] += 1

    # post-process themes
    for token, stat in token_stats.items():
        best_name = stat["names"].most_common(1)[0][0] if stat["names"] else token
        best_symbol = stat["symbols"].most_common(1)[0][0] if stat["symbols"] else ""

        themes = classify_token_themes(best_name, best_symbol, cfg)
        for theme in themes:
            stat["themes"][theme] += 1

        # small score bonuses for structurally stronger tokens
        if stat["has_launch"] and stat["has_raydium"]:
            stat["score"] += 1.4

        if stat["has_velocity"]:
            stat["score"] += 0.8

        if stat["has_liquidity"]:
            stat["score"] += 0.5

        if stat["signal_count"] > 1:
            stat["score"] += math.log(stat["signal_count"], 2) * 0.3

    return dict(token_stats)


# ---------------------------------------------------
# SIGNAL BUILDERS
# ---------------------------------------------------

def build_trending_signals(
    ranked_tokens: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> List[Signal]:
    signals: List[Signal] = []
    now = utc_now()
    min_score_to_emit = safe_float(cfg.get("min_score_to_emit", 2.0), 2.0)

    for rank, stat in enumerate(ranked_tokens, start=1):
        token = stat["token"]
        score = safe_float(stat["score"])
        if score < min_score_to_emit:
            continue

        best_name = stat["names"].most_common(1)[0][0] if stat["names"] else token
        best_symbol = stat["symbols"].most_common(1)[0][0] if stat["symbols"] else token[:6]
        themes = [x[0] for x in stat["themes"].most_common(3)]
        top_types = [x[0] for x in stat["types"].most_common(4)]

        signals.append(
            Signal(
                timestamp=now,
                source="toknclaw",
                signal_type="solana_memecoin_trending",
                entity=token,
                title=f"Trending Solana memecoin #{rank}",
                summary=(
                    f"{best_name} ({best_symbol}) ranked #{rank} with score {score:.2f}. "
                    f"signal_count={stat['signal_count']}. "
                    f"top_types={', '.join(top_types) if top_types else 'none'}. "
                    f"themes={', '.join(themes) if themes else 'none'}."
                ),
                confidence=0.82,
                sentiment_score=0.34,
                raw_url=f"https://solscan.io/token/{token}",
            )
        )

        if stat["has_velocity"]:
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_memecoin_velocity",
                    entity=token,
                    title=f"Memecoin velocity building for rank #{rank}",
                    summary=(
                        f"{best_name} shows emerging velocity with score {score:.2f} "
                        f"and {stat['types'].get('solana_volume_velocity', 0)} velocity signals."
                    ),
                    confidence=0.79,
                    sentiment_score=0.39,
                    raw_url=f"https://solscan.io/token/{token}",
                )
            )

    return signals


def build_summary_signals(
    ranked_tokens: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> List[Signal]:
    signals: List[Signal] = []
    now = utc_now()

    if not ranked_tokens:
        return signals

    top_n = int(cfg.get("top_n_tokens", 12))
    leaders = ranked_tokens[:top_n]

    leaderboard_text = ", ".join(
        f"{idx + 1}. {row['token'][:8]}({safe_float(row['score']):.2f})"
        for idx, row in enumerate(leaders[:8])
    )

    signals.append(
        Signal(
            timestamp=now,
            source="toknclaw",
            signal_type="solana_memecoin_leaderboard",
            entity="SOLANA_MEME",
            title="Solana memecoin leaderboard updated",
            summary=f"Top ranked Solana memecoins: {leaderboard_text}",
            confidence=0.78,
            sentiment_score=0.30,
            raw_url=None,
        )
    )

    if bool(cfg.get("emit_memecoin_of_the_day", True)):
        top = leaders[0]
        token = top["token"]
        name = top["names"].most_common(1)[0][0] if top["names"] else token
        symbol = top["symbols"].most_common(1)[0][0] if top["symbols"] else token[:6]

        signals.append(
            Signal(
                timestamp=now,
                source="toknclaw",
                signal_type="solana_memecoin_of_the_day",
                entity=token,
                title="Solana memecoin of the day",
                summary=(
                    f"{name} ({symbol}) is the current ToknClaw memecoin of the day "
                    f"with score {safe_float(top['score']):.2f} and {top['signal_count']} recent signals."
                ),
                confidence=0.83,
                sentiment_score=0.42,
                raw_url=f"https://solscan.io/token/{token}",
            )
        )

    if bool(cfg.get("emit_bitsy_watchlist", True)):
        funny_rows = [row for row in leaders if int(row.get("funny_hits", 0)) > 0][:5]

        if funny_rows:
            funny_text = ", ".join(
                row["names"].most_common(1)[0][0] if row["names"] else row["token"][:8]
                for row in funny_rows
            )

            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_bitsy_watchlist",
                    entity="BITSY",
                    title="Bitsy watchlist updated",
                    summary=f"Bitsy meme watchlist: {funny_text}",
                    confidence=0.76,
                    sentiment_score=0.51,
                    raw_url=None,
                )
            )

    if bool(cfg.get("emit_name_theme_summary", True)):
        theme_counter: Counter = Counter()

        for row in leaders:
            for theme, count in row["themes"].items():
                theme_counter[theme] += count

        if theme_counter:
            top_themes = ", ".join(
                f"{theme}({count})" for theme, count in theme_counter.most_common(5)
            )

            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_name_theme_summary",
                    entity="SOLANA_MEME_THEMES",
                    title="Solana memecoin naming themes updated",
                    summary=f"Top memecoin naming themes: {top_themes}",
                    confidence=0.74,
                    sentiment_score=0.25,
                    raw_url=None,
                )
            )

    return signals


# ---------------------------------------------------
# PUBLIC COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="solana_pumpfun_leaderboard",
    priority=2,
    tags=["solana", "pumpfun", "leaderboard", "culture", "broadcast", "trading"],
    category="onchain",
)
def fetch_solana_pumpfun_leaderboard_signals() -> List[Signal]:
    started = time.time()
    cfg = load_leaderboard_config()
    signals: List[Signal] = []

    if not bool(cfg.get("enabled", True)):
        info_log("disabled by config")
        return signals

    lake = load_signal_lake()
    raw_rows = object_signals_only(lake.get("signals", []))

    if not raw_rows:
        info_log("signal lake empty")
        return signals

    token_stats = build_token_stats(raw_rows, cfg)

    if not token_stats:
        info_log("no token stats built")
        return signals

    ranked_tokens = sorted(
        token_stats.values(),
        key=lambda row: (-safe_float(row.get("score")), -int(row.get("signal_count", 0)), row.get("token", "")),
    )[: int(cfg.get("max_tokens_to_score", 200))]

    signals.extend(build_trending_signals(ranked_tokens, cfg))
    signals.extend(build_summary_signals(ranked_tokens, cfg))

    max_signals_per_run = int(cfg.get("max_signals_per_run", 40))
    if len(signals) > max_signals_per_run:
        signals = signals[:max_signals_per_run]
        debug_log(f"max signal cap reached max_per_run={max_signals_per_run}")

    runtime = round(time.time() - started, 2)
    info_log(
        f"rows={len(raw_rows)} "
        f"tokens_scored={len(token_stats)} "
        f"signals_returned={len(signals)} "
        f"runtime={runtime}s"
    )

    return signals
