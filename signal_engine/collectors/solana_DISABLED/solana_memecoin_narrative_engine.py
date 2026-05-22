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
# MODULE: solana_memecoin_narrative_engine
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
Solana Memecoin Narrative Engine

Purpose
-------
Builds narrative-ready Solana memecoin signals from the signal lake.

This engine is intended to bridge raw Solana collection into:
• ToknNews broadcast enrichment
• meme coin of the day selection
• Bitsy funny-name segments
• cultural/theme summaries
• narrative candidates for anchor scripting
• OpenClaw agent consumption

Inputs
------
Reads from:
• /opt/toknclaw/data/signal_lake.json

Uses signal types such as:
• solana_pumpfun_activity
• solana_pumpfun_launch
• solana_funny_name_candidate
• solana_token_name_detected
• solana_token_symbol_detected
• solana_token_name_theme
• solana_memecoin_trending
• solana_memecoin_velocity
• solana_jupiter_swap
• solana_jupiter_swap_activity
• solana_raydium_pool_init
• solana_raydium_pool_activity
• solana_liquidity_event
• solana_liquidity_depth
• solana_volume_velocity
• solana_mev_activity

Outputs
-------
Emits narrative-level Signal rows such as:
• solana_memecoin_of_the_day
• solana_bitsy_watchlist
• solana_name_theme_summary
• solana_culture_rotation
• solana_memecoin_narrative_candidate

Agent Readiness
---------------
OpenClaw agents should tune:
• /opt/toknclaw/config/solana_memecoin_narrative_engine.json

instead of editing this file.

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


CONFIG_FILE = "solana_memecoin_narrative_engine.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "lookback_signal_count": 4000,
    "max_tokens_scored": 100,
    "max_narrative_candidates": 8,
    "max_bitsy_watchlist": 5,
    "max_theme_examples": 5,
    "min_score_for_narrative": 3.0,
    "weights": {
        "solana_pumpfun_launch": 3.0,
        "solana_pumpfun_activity": 1.0,
        "solana_memecoin_trending": 3.5,
        "solana_memecoin_velocity": 2.5,
        "solana_jupiter_swap": 1.0,
        "solana_jupiter_swap_activity": 1.2,
        "solana_raydium_pool_init": 2.5,
        "solana_raydium_pool_activity": 1.2,
        "solana_liquidity_event": 1.4,
        "solana_liquidity_depth": 1.0,
        "solana_volume_velocity": 2.0,
        "solana_funny_name_candidate": 1.5,
        "solana_token_name_detected": 0.5,
        "solana_token_symbol_detected": 0.3,
        "solana_token_name_theme": 1.0,
        "solana_mev_activity": -0.6,
        "solana_thin_liquidity_alert": -1.2,
    },
    "bitsy_keywords": [
        "dog",
        "cat",
        "ai",
        "pepe",
        "bonk",
        "trump",
        "elon",
        "moon",
        "frog",
        "meme",
        "coin",
        "pump",
        "cash",
        "inu",
        "wojak",
        "based",
        "sigma",
        "degen",
    ],
    "theme_keywords": {
        "ai": ["ai", "agent", "gpt", "bot", "neural", "brain", "quant"],
        "animals": ["dog", "cat", "inu", "frog", "pepe", "shark", "whale"],
        "politics": ["trump", "maga", "president", "vote", "elon", "rfk"],
        "money": ["cash", "money", "usd", "dollar", "million", "bank", "alpha"],
        "internet": ["meme", "wojak", "based", "sigma", "viral", "lol", "rekt"],
    },
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def load_engine_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)

    if not isinstance(cfg, dict):
        return dict(DEFAULT_CONFIG)

    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)

    base_weights = dict(DEFAULT_CONFIG["weights"])
    user_weights = cfg.get("weights", {})
    if isinstance(user_weights, dict):
        base_weights.update(user_weights)
    merged["weights"] = base_weights

    base_themes = dict(DEFAULT_CONFIG["theme_keywords"])
    user_themes = cfg.get("theme_keywords", {})
    if isinstance(user_themes, dict):
        for key, value in user_themes.items():
            if isinstance(value, list):
                base_themes[str(key).strip().lower()] = [str(x).strip().lower() for x in value if str(x).strip()]
    merged["theme_keywords"] = base_themes

    bitsy_keywords = cfg.get("bitsy_keywords", DEFAULT_CONFIG["bitsy_keywords"])
    if isinstance(bitsy_keywords, list):
        merged["bitsy_keywords"] = [str(x).strip().lower() for x in bitsy_keywords if str(x).strip()]
    else:
        merged["bitsy_keywords"] = list(DEFAULT_CONFIG["bitsy_keywords"])

    return merged


def object_rows_only(rows: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for row in rows or []:
        if isinstance(row, dict):
            out.append(row)

    return out


def sget(row: Dict[str, Any], key: str, default: Any = None) -> Any:
    if not isinstance(row, dict):
        return default
    return row.get(key, default)


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def clean_lower(value: Any) -> str:
    return clean_text(value).lower()


def is_probable_token_entity(entity: str) -> bool:
    entity = clean_text(entity)

    if not entity:
        return False

    blocked = {
        "SOLANA",
        "PUMPFUN",
        "PUMPFUN_ACTIVITY",
        "SOLANA_ALPHA",
        "SOLANA_MEMECOINS",
        "SOLANA_CULTURE",
        "SOLANA_BITSY",
    }

    if entity.upper() in blocked:
        return False

    if "/" in entity:
        return False

    return len(entity) >= 20


def parse_name_from_summary(summary: str, entity: str) -> str:
    summary = clean_text(summary)

    markers = [
        "name candidate spotted:",
        "token name:",
        "name detected:",
        "resolved metadata:",
        "name=",
    ]

    lower = summary.lower()

    for marker in markers:
        idx = lower.find(marker)
        if idx >= 0:
            extracted = summary[idx + len(marker):].strip()
            if extracted:
                return extracted

    return entity


def parse_symbol_from_summary(summary: str) -> str:
    summary = clean_text(summary)
    lower = summary.lower()

    markers = [
        "symbol:",
        "symbol=",
    ]

    for marker in markers:
        idx = lower.find(marker)
        if idx >= 0:
            extracted = summary[idx + len(marker):].strip()
            if extracted:
                return extracted.split()[0].strip(" ,.;:()[]{}")
    return ""


def detect_themes(name_text: str, theme_keywords: Dict[str, List[str]]) -> List[str]:
    text = clean_lower(name_text)
    hits: List[str] = []

    if not text:
        return hits

    for theme, keywords in theme_keywords.items():
        for kw in keywords:
            if kw in text:
                hits.append(theme)
                break

    return hits


def is_bitsy_candidate(name_text: str, bitsy_keywords: List[str]) -> bool:
    text = clean_lower(name_text)

    if not text:
        return False

    for kw in bitsy_keywords:
        if kw in text:
            return True

    return False


def score_rows(
    rows: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Tuple[List[Tuple[str, float]], Dict[str, Dict[str, Any]], Counter]:
    weights = cfg.get("weights", {})
    theme_keywords = cfg.get("theme_keywords", {})
    bitsy_keywords = cfg.get("bitsy_keywords", [])

    token_map: Dict[str, Dict[str, Any]] = {}
    theme_counter: Counter = Counter()

    for row in rows:
        signal_type = clean_text(sget(row, "signal_type"))
        entity = clean_text(sget(row, "entity"))
        title = clean_text(sget(row, "title"))
        summary = clean_text(sget(row, "summary"))

        token = entity if is_probable_token_entity(entity) else ""

        if not token and signal_type in {
            "solana_memecoin_trending",
            "solana_memecoin_velocity",
        }:
            token = entity if entity else ""

        if not token or not is_probable_token_entity(token):
            continue

        bucket = token_map.setdefault(
            token,
            {
                "token": token,
                "score": 0.0,
                "signal_counts": Counter(),
                "titles": [],
                "summaries": [],
                "names": set(),
                "symbols": set(),
                "themes": Counter(),
                "funny_hits": 0,
                "positive_hits": 0,
                "negative_hits": 0,
            },
        )

        weight = float(weights.get(signal_type, 0.0))
        bucket["score"] += weight
        bucket["signal_counts"][signal_type] += 1

        if title:
            bucket["titles"].append(title)
        if summary:
            bucket["summaries"].append(summary)

        if weight > 0:
            bucket["positive_hits"] += 1
        elif weight < 0:
            bucket["negative_hits"] += 1

        if signal_type == "solana_token_name_detected":
            name_value = parse_name_from_summary(summary, token)
            if name_value:
                bucket["names"].add(name_value)

        if signal_type == "solana_funny_name_candidate":
            funny_name = parse_name_from_summary(summary, token)
            if funny_name:
                bucket["names"].add(funny_name)
            bucket["funny_hits"] += 1

        if signal_type == "solana_token_symbol_detected":
            symbol_value = parse_symbol_from_summary(summary)
            if symbol_value:
                bucket["symbols"].add(symbol_value)

        if signal_type == "solana_token_name_theme":
            theme_from_summary = clean_lower(summary)
            for theme_key in theme_keywords.keys():
                if theme_key in theme_from_summary:
                    bucket["themes"][theme_key] += 1
                    theme_counter[theme_key] += 1

        for known_name in list(bucket["names"]):
            for theme in detect_themes(known_name, theme_keywords):
                bucket["themes"][theme] += 1
                theme_counter[theme] += 1

            if is_bitsy_candidate(known_name, bitsy_keywords):
                bucket["funny_hits"] += 1

    scored = sorted(
        [(token, round(meta["score"], 4)) for token, meta in token_map.items()],
        key=lambda x: x[1],
        reverse=True,
    )

    max_tokens_scored = int(cfg.get("max_tokens_scored", 100))
    scored = scored[:max_tokens_scored]

    filtered_map = {token: token_map[token] for token, _ in scored}

    return scored, filtered_map, theme_counter


def build_reason_list(meta: Dict[str, Any]) -> List[str]:
    signal_counts: Counter = meta.get("signal_counts", Counter())
    reasons: List[str] = []

    priority_order = [
        "solana_memecoin_trending",
        "solana_memecoin_velocity",
        "solana_pumpfun_launch",
        "solana_raydium_pool_init",
        "solana_volume_velocity",
        "solana_jupiter_swap_activity",
        "solana_liquidity_event",
        "solana_funny_name_candidate",
        "solana_token_name_theme",
    ]

    labels = {
        "solana_memecoin_trending": "leaderboard momentum",
        "solana_memecoin_velocity": "velocity build",
        "solana_pumpfun_launch": "fresh launch",
        "solana_raydium_pool_init": "pool initialization",
        "solana_volume_velocity": "volume spike",
        "solana_jupiter_swap_activity": "swap activity",
        "solana_liquidity_event": "liquidity activity",
        "solana_funny_name_candidate": "funny name potential",
        "solana_token_name_theme": "theme alignment",
    }

    for signal_type in priority_order:
        count = int(signal_counts.get(signal_type, 0))
        if count > 0:
            label = labels.get(signal_type, signal_type)
            reasons.append(f"{label} x{count}")

    return reasons[:4]


def pick_display_name(meta: Dict[str, Any]) -> str:
    names = sorted([clean_text(x) for x in meta.get("names", set()) if clean_text(x)])
    symbols = sorted([clean_text(x) for x in meta.get("symbols", set()) if clean_text(x)])

    if names:
        return names[0]

    if symbols:
        return symbols[0]

    return clean_text(meta.get("token"))


def build_memecoin_of_the_day(
    scored: List[Tuple[str, float]],
    token_map: Dict[str, Dict[str, Any]],
) -> List[Signal]:
    if not scored:
        return []

    token, score = scored[0]
    meta = token_map[token]

    display_name = pick_display_name(meta)
    reasons = build_reason_list(meta)
    theme_list = [theme for theme, _ in meta.get("themes", Counter()).most_common(3)]

    summary_parts = [
        f"{display_name} selected as memecoin of the day",
        f"score={score:.2f}",
    ]

    if reasons:
        summary_parts.append("drivers=" + ", ".join(reasons))

    if theme_list:
        summary_parts.append("themes=" + ", ".join(theme_list))

    return [
        Signal(
            timestamp=utc_now(),
            source="toknclaw",
            signal_type="solana_memecoin_of_the_day",
            entity=token,
            title="Solana memecoin of the day",
            summary=" | ".join(summary_parts),
            confidence=0.83,
            sentiment_score=0.42,
            raw_url=None,
        )
    ]


def build_bitsy_watchlist(
    scored: List[Tuple[str, float]],
    token_map: Dict[str, Dict[str, Any]],
    cfg: Dict[str, Any],
) -> List[Signal]:
    signals: List[Signal] = []
    max_items = int(cfg.get("max_bitsy_watchlist", 5))

    funny_tokens: List[Tuple[str, float]] = []

    for token, score in scored:
        meta = token_map[token]
        if int(meta.get("funny_hits", 0)) > 0:
            funny_tokens.append((token, score))

    funny_tokens = funny_tokens[:max_items]

    for rank, (token, score) in enumerate(funny_tokens, start=1):
        meta = token_map[token]
        display_name = pick_display_name(meta)
        theme_list = [theme for theme, _ in meta.get("themes", Counter()).most_common(2)]
        theme_suffix = f" themes={', '.join(theme_list)}" if theme_list else ""

        signals.append(
            Signal(
                timestamp=utc_now(),
                source="toknclaw",
                signal_type="solana_bitsy_watchlist",
                entity=token,
                title=f"Bitsy watchlist memecoin #{rank}",
                summary=(
                    f"{display_name} flagged for Bitsy segment | "
                    f"score={score:.2f} | "
                    f"funny_hits={int(meta.get('funny_hits', 0))}"
                    f"{theme_suffix}"
                ),
                confidence=0.79,
                sentiment_score=0.33,
                raw_url=None,
            )
        )

    return signals


def build_name_theme_summary(
    theme_counter: Counter,
    token_map: Dict[str, Dict[str, Any]],
    cfg: Dict[str, Any],
) -> List[Signal]:
    if not theme_counter:
        return []

    max_theme_examples = int(cfg.get("max_theme_examples", 5))
    top_themes = theme_counter.most_common(5)

    theme_signals: List[Signal] = []

    for theme, count in top_themes:
        example_tokens: List[str] = []

        for token, meta in token_map.items():
            if meta.get("themes", Counter()).get(theme, 0) > 0:
                example_tokens.append(pick_display_name(meta))

        example_tokens = example_tokens[:max_theme_examples]

        theme_signals.append(
            Signal(
                timestamp=utc_now(),
                source="toknclaw",
                signal_type="solana_name_theme_summary",
                entity=f"THEME_{theme.upper()}",
                title=f"Solana name theme summary: {theme}",
                summary=(
                    f"Theme '{theme}' appeared {count} times across active memecoins"
                    + (f" | examples={', '.join(example_tokens)}" if example_tokens else "")
                ),
                confidence=0.76,
                sentiment_score=0.22,
                raw_url=None,
            )
        )

    return theme_signals


def build_culture_rotation(theme_counter: Counter) -> List[Signal]:
    if not theme_counter:
        return []

    top_themes = theme_counter.most_common(3)

    return [
        Signal(
            timestamp=utc_now(),
            source="toknclaw",
            signal_type="solana_culture_rotation",
            entity="SOLANA_CULTURE",
            title="Solana culture rotation detected",
            summary="Dominant memecoin naming themes: " + ", ".join(
                [f"{theme}({count})" for theme, count in top_themes]
            ),
            confidence=0.77,
            sentiment_score=0.24,
            raw_url=None,
        )
    ]


def build_narrative_candidates(
    scored: List[Tuple[str, float]],
    token_map: Dict[str, Dict[str, Any]],
    cfg: Dict[str, Any],
) -> List[Signal]:
    signals: List[Signal] = []
    max_candidates = int(cfg.get("max_narrative_candidates", 8))
    min_score = float(cfg.get("min_score_for_narrative", 3.0))

    for rank, (token, score) in enumerate(scored[:max_candidates], start=1):
        if score < min_score:
            continue

        meta = token_map[token]
        display_name = pick_display_name(meta)
        reasons = build_reason_list(meta)
        theme_list = [theme for theme, _ in meta.get("themes", Counter()).most_common(3)]

        summary_parts = [
            f"{display_name} narrative candidate rank={rank}",
            f"score={score:.2f}",
        ]

        if reasons:
            summary_parts.append("drivers=" + ", ".join(reasons))

        if theme_list:
            summary_parts.append("themes=" + ", ".join(theme_list))

        summary_parts.append(
            f"positive_hits={int(meta.get('positive_hits', 0))} "
            f"negative_hits={int(meta.get('negative_hits', 0))}"
        )

        signals.append(
            Signal(
                timestamp=utc_now(),
                source="toknclaw",
                signal_type="solana_memecoin_narrative_candidate",
                entity=token,
                title=f"Solana narrative candidate #{rank}",
                summary=" | ".join(summary_parts),
                confidence=0.81,
                sentiment_score=0.36 if score >= 0 else -0.2,
                raw_url=None,
            )
        )

    return signals


@register_collector(
    name="solana_memecoin_narrative_engine",
    priority=2,
    tags=["solana", "narrative", "culture", "broadcast", "agents"],
    category="onchain",
)
def fetch_solana_memecoin_narrative_signals() -> List[Signal]:
    started = time.time()
    cfg = load_engine_config()
    signals: List[Signal] = []

    if not bool(cfg.get("enabled", True)):
        print("[SOLANA NARRATIVE] disabled by config")
        return signals

    lake = load_signal_lake()
    raw_rows = object_rows_only(lake.get("signals", []))

    lookback_signal_count = int(cfg.get("lookback_signal_count", 4000))
    rows = raw_rows[-lookback_signal_count:]

    scored, token_map, theme_counter = score_rows(rows, cfg)

    if not scored:
        print("[SOLANA NARRATIVE] no scored tokens")
        return signals

    signals.extend(build_memecoin_of_the_day(scored, token_map))
    signals.extend(build_bitsy_watchlist(scored, token_map, cfg))
    signals.extend(build_name_theme_summary(theme_counter, token_map, cfg))
    signals.extend(build_culture_rotation(theme_counter))
    signals.extend(build_narrative_candidates(scored, token_map, cfg))

    runtime = round(time.time() - started, 2)
    print(
        f"[SOLANA NARRATIVE] rows={len(rows)} "
        f"tokens_scored={len(scored)} "
        f"themes={len(theme_counter)} "
        f"signals_returned={len(signals)} "
        f"runtime={runtime}s"
    )

    return signals
