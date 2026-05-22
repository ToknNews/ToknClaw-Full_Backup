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
# MODULE: solana_token_name_intelligence
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
Solana Token Name Intelligence Collector

Purpose
-------
Analyze newly observed Solana memecoin/token launch entities and emit
name-level intelligence for:

• ToknNews culture segments
• Bitsy funniest-name commentary
• meme trend detection
• retail narrative enrichment
• social post generation
• alerting pipelines
• OpenClaw agent reasoning
• alpha context overlays

Data Inputs
-----------
• /opt/toknclaw/data/signal_lake.json
• upstream launch/activity signals such as:
  - solana_pumpfun_launch
  - solana_pumpfun_activity
  - solana_token_created
  - solana_raydium_pool_init
  - solana_jupiter_swap

Outputs
-------
• solana_token_name_detected
• solana_funny_name_candidate
• solana_token_name_theme
• solana_memecoin_name_summary

Design Notes
------------
• no live RPC dependency
• low-cost enrichment-only collector
• agent-tunable via config file
• safe for frequent execution
• intended for broadcast + research workflows

Primary Config
--------------
/opt/toknclaw/config/solana_token_name_intelligence.json

Author: TOKN Systems
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from signal_engine.collectors.registry import register_collector
from models.signal import Signal


SIGNAL_LAKE_PATH = Path("/opt/toknclaw/data/signal_lake.json")
CONFIG_PATH = Path("/opt/toknclaw/config/solana_token_name_intelligence.json")

DEBUG = os.getenv("TOKN_DEBUG_COLLECTORS", "1") == "1"

DEFAULT_MAX_SOURCE_ROWS = int(os.getenv("TOKN_SOL_NAME_INTELLIGENCE_MAX_SOURCE_ROWS", "3000"))
DEFAULT_MAX_TOKENS = int(os.getenv("TOKN_SOL_NAME_INTELLIGENCE_MAX_TOKENS", "150"))
DEFAULT_MAX_SIGNALS = int(os.getenv("TOKN_SOL_NAME_INTELLIGENCE_MAX_SIGNALS", "120"))


DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "max_source_rows": DEFAULT_MAX_SOURCE_ROWS,
    "max_tokens": DEFAULT_MAX_TOKENS,
    "max_signals": DEFAULT_MAX_SIGNALS,
    "source_signal_types": [
        "solana_pumpfun_launch",
        "solana_pumpfun_activity",
        "solana_token_created",
        "solana_raydium_pool_init",
        "solana_jupiter_swap",
    ],
    "funny_score_threshold": 2.2,
    "theme_score_threshold": 1.0,
    "summary_top_n": 10,
    "meme_keywords": [
        "pump",
        "moon",
        "dog",
        "cat",
        "frog",
        "pepe",
        "bonk",
        "ai",
        "elon",
        "trump",
        "baby",
        "inu",
        "coin",
        "cash",
        "degen",
        "wojak",
        "meme",
        "sigma",
        "chad",
        "giga",
        "cult",
        "rekt",
        "send",
        "lambo",
        "casino",
        "ape",
        "rizz",
        "goblin",
        "wizard",
        "tax",
        "wife",
        "mortgage",
        "grandma",
        "insurance",
        "quant",
        "fart",
    ],
    "theme_map": {
        "animals": [
            "dog",
            "cat",
            "frog",
            "inu",
            "shark",
            "panda",
            "monkey",
            "ape",
            "whale",
            "rat",
            "cow",
            "goat",
        ],
        "finance": [
            "cash",
            "coin",
            "bank",
            "mortgage",
            "fund",
            "tax",
            "yield",
            "alpha",
            "beta",
            "pump",
            "dump",
            "lambo",
            "insurance",
        ],
        "internet": [
            "meme",
            "wojak",
            "chad",
            "sigma",
            "rizz",
            "viral",
            "npc",
            "giga",
            "brainrot",
            "tiktok",
        ],
        "politics": [
            "trump",
            "biden",
            "maga",
            "freedom",
            "president",
            "senate",
        ],
        "technology": [
            "ai",
            "agent",
            "quant",
            "bot",
            "gpu",
            "robot",
            "cloud",
            "chain",
        ],
        "degenerate": [
            "degen",
            "casino",
            "rekt",
            "send",
            "rug",
            "fart",
            "goblin",
            "wife",
            "grandma",
        ],
    },
}


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def debug_log(message: str) -> None:
    if DEBUG:
        print(f"[SOLANA NAME INTEL] {message}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)

    try:
        with open(CONFIG_PATH) as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return dict(DEFAULT_CONFIG)

        merged = dict(DEFAULT_CONFIG)
        merged.update(raw)

        if not isinstance(merged.get("source_signal_types"), list):
            merged["source_signal_types"] = DEFAULT_CONFIG["source_signal_types"]

        if not isinstance(merged.get("meme_keywords"), list):
            merged["meme_keywords"] = DEFAULT_CONFIG["meme_keywords"]

        if not isinstance(merged.get("theme_map"), dict):
            merged["theme_map"] = DEFAULT_CONFIG["theme_map"]

        return merged

    except Exception as e:
        debug_log(f"config load failed error={e}")
        return dict(DEFAULT_CONFIG)


def load_signal_lake() -> Dict[str, Any]:
    if not SIGNAL_LAKE_PATH.exists():
        debug_log("signal lake missing")
        return {"signals": [], "collector_runs": {}, "updated_at": None}

    try:
        with open(SIGNAL_LAKE_PATH) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"signals": [], "collector_runs": {}, "updated_at": None}
        return data
    except Exception as e:
        debug_log(f"signal lake load failed error={e}")
        return {"signals": [], "collector_runs": {}, "updated_at": None}


def tokenize(value: str) -> List[str]:
    value = value or ""
    split_value = re.sub(r"[^A-Za-z0-9]+", " ", value)
    camel_split = re.sub(r"([a-z])([A-Z])", r"\1 \2", split_value)
    tokens = [x.lower() for x in camel_split.split() if x.strip()]
    return tokens


def extract_name_candidate(entity: str) -> Optional[str]:
    if not isinstance(entity, str):
        return None

    entity = entity.strip()
    if not entity:
        return None

    if entity.endswith("pump"):
        return entity[:-4]

    return entity


def short_token(token: str, head: int = 6, tail: int = 4) -> str:
    if len(token) <= head + tail + 2:
        return token
    return f"{token[:head]}...{token[-tail:]}"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def derive_funny_score(name_candidate: str, tokens: List[str], meme_keywords: Set[str]) -> float:
    score = 0.0

    # base keyword hits
    for t in tokens:
        if t in meme_keywords:
            score += 1.0

    # exaggerated format boosts
    if any(ch.isdigit() for ch in name_candidate):
        score += 0.15

    if len(tokens) >= 3:
        score += 0.35

    if len(name_candidate) >= 18:
        score += 0.25

    # stronger comedic/degenerate terms
    boosted_terms = {
        "fart": 1.2,
        "mortgage": 1.0,
        "insurance": 1.0,
        "grandma": 1.0,
        "wife": 0.9,
        "goblin": 0.8,
        "casino": 0.8,
        "degen": 0.8,
        "rizz": 0.8,
        "wojak": 0.7,
        "chad": 0.7,
        "sigma": 0.7,
        "lambo": 0.7,
        "tax": 0.6,
    }

    for t in tokens:
        score += boosted_terms.get(t, 0.0)

    return round(score, 2)


def derive_themes(tokens: List[str], theme_map: Dict[str, List[str]], threshold: float) -> List[str]:
    theme_scores: Dict[str, float] = {}

    token_set = set(tokens)

    for theme_name, keywords in theme_map.items():
        score = 0.0
        for kw in keywords:
            if kw in token_set:
                score += 1.0
        if score >= threshold:
            theme_scores[theme_name] = score

    ordered = sorted(theme_scores.items(), key=lambda x: (-x[1], x[0]))
    return [name for name, _ in ordered]


def build_source_rows(
    signals: Iterable[Dict[str, Any]],
    allowed_types: Set[str],
    max_source_rows: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for row in signals:
        if not isinstance(row, dict):
            continue

        signal_type = row.get("signal_type")
        entity = row.get("entity")

        if signal_type not in allowed_types:
            continue

        if not isinstance(entity, str) or not entity.strip():
            continue

        rows.append(row)

    rows.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
    return rows[:max_source_rows]


def build_token_stats(
    source_rows: List[Dict[str, Any]],
    max_tokens: int,
) -> Dict[str, Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    seen_order: List[str] = []

    for row in source_rows:
        entity = str(row.get("entity", "")).strip()
        if not entity:
            continue

        if entity not in stats:
            stats[entity] = {
                "entity": entity,
                "first_seen": row.get("timestamp"),
                "last_seen": row.get("timestamp"),
                "source_signal_types": Counter(),
                "titles": Counter(),
                "occurrences": 0,
            }
            seen_order.append(entity)

        bucket = stats[entity]
        bucket["occurrences"] += 1
        bucket["last_seen"] = row.get("timestamp")
        signal_type = str(row.get("signal_type", "")).strip()
        title = str(row.get("title", "")).strip()

        if signal_type:
            bucket["source_signal_types"][signal_type] += 1
        if title:
            bucket["titles"][title] += 1

    trimmed_entities = seen_order[:max_tokens]
    return {entity: stats[entity] for entity in trimmed_entities}


# ---------------------------------------------------
# COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="solana_token_name_intelligence",
    priority=2,
    tags=["solana", "names", "culture", "broadcast", "bitsy"],
    category="onchain",
)
def fetch_solana_token_name_intelligence_signals() -> List[Signal]:
    started = time.time()
    cfg = load_config()

    if not bool(cfg.get("enabled", True)):
        debug_log("collector disabled by config")
        return []

    max_source_rows = int(cfg.get("max_source_rows", DEFAULT_MAX_SOURCE_ROWS))
    max_tokens = int(cfg.get("max_tokens", DEFAULT_MAX_TOKENS))
    max_signals = int(cfg.get("max_signals", DEFAULT_MAX_SIGNALS))
    funny_score_threshold = safe_float(cfg.get("funny_score_threshold", 2.2), 2.2)
    theme_score_threshold = safe_float(cfg.get("theme_score_threshold", 1.0), 1.0)
    summary_top_n = int(cfg.get("summary_top_n", 10))

    meme_keywords = {
        str(x).strip().lower()
        for x in cfg.get("meme_keywords", [])
        if str(x).strip()
    }

    theme_map = {
        str(k).strip().lower(): [
            str(x).strip().lower()
            for x in (v or [])
            if str(x).strip()
        ]
        for k, v in (cfg.get("theme_map", {}) or {}).items()
    }

    allowed_types = {
        str(x).strip()
        for x in cfg.get("source_signal_types", [])
        if str(x).strip()
    }

    lake = load_signal_lake()
    lake_signals = lake.get("signals") or []

    source_rows = build_source_rows(
        signals=lake_signals,
        allowed_types=allowed_types,
        max_source_rows=max_source_rows,
    )

    token_stats = build_token_stats(source_rows, max_tokens=max_tokens)

    now = utc_now()
    out: List[Signal] = []
    funny_candidates: List[Dict[str, Any]] = []
    theme_counter: Counter[str] = Counter()

    for entity, stats in token_stats.items():
        name_candidate = extract_name_candidate(entity)
        if not name_candidate:
            continue

        tokens = tokenize(name_candidate)
        if not tokens:
            continue

        funny_score = derive_funny_score(
            name_candidate=name_candidate,
            tokens=tokens,
            meme_keywords=meme_keywords,
        )

        themes = derive_themes(
            tokens=tokens,
            theme_map=theme_map,
            threshold=theme_score_threshold,
        )

        primary_title = None
        if stats["titles"]:
            primary_title = stats["titles"].most_common(1)[0][0]

        out.append(
            Signal(
                timestamp=now,
                source="toknclaw",
                signal_type="solana_token_name_detected",
                entity=entity,
                title="Solana token name intelligence detected",
                summary=(
                    f"Token {short_token(entity)} name candidate analyzed as "
                    f"'{name_candidate}' with funny_score={funny_score:.2f} "
                    f"and themes={themes or ['none']}"
                ),
                confidence=0.71,
                sentiment_score=0.18 if funny_score > 0 else 0.0,
                raw_url=f"https://solscan.io/token/{entity}",
            )
        )

        if funny_score >= funny_score_threshold:
            funny_candidates.append(
                {
                    "entity": entity,
                    "name_candidate": name_candidate,
                    "funny_score": funny_score,
                    "occurrences": stats["occurrences"],
                }
            )

            out.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_funny_name_candidate",
                    entity=entity,
                    title="Funny Solana token name candidate detected",
                    summary=(
                        f"Token '{name_candidate}' flagged for culture commentary "
                        f"with funny_score={funny_score:.2f}"
                    ),
                    confidence=0.77,
                    sentiment_score=0.42,
                    raw_url=f"https://solscan.io/token/{entity}",
                )
            )

        for theme in themes[:2]:
            theme_counter[theme] += 1
            out.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_token_name_theme",
                    entity=entity,
                    title=f"Solana token name theme detected: {theme}",
                    summary=(
                        f"Token '{name_candidate}' classified under theme '{theme}'. "
                        f"Primary upstream title: {primary_title or 'unknown'}"
                    ),
                    confidence=0.69,
                    sentiment_score=0.12,
                    raw_url=f"https://solscan.io/token/{entity}",
                )
            )

        if len(out) >= max_signals:
            debug_log(f"max signal cap reached max_signals={max_signals}")
            break

    if funny_candidates or theme_counter:
        funny_candidates = sorted(
            funny_candidates,
            key=lambda x: (-x["funny_score"], -x["occurrences"], x["name_candidate"].lower()),
        )
        top_funny = funny_candidates[:summary_top_n]
        top_themes = theme_counter.most_common(5)

        summary_parts: List[str] = []

        if top_funny:
            funny_text = ", ".join(
                f"{row['name_candidate']}({row['funny_score']:.2f})"
                for row in top_funny[:5]
            )
            summary_parts.append(f"top funny names: {funny_text}")

        if top_themes:
            theme_text = ", ".join(f"{name}({count})" for name, count in top_themes)
            summary_parts.append(f"top themes: {theme_text}")

        out.append(
            Signal(
                timestamp=now,
                source="toknclaw",
                signal_type="solana_memecoin_name_summary",
                entity="SOLANA_NAME_INTELLIGENCE",
                title="Solana memecoin name intelligence summary",
                summary="; ".join(summary_parts) if summary_parts else "No significant naming patterns detected",
                confidence=0.74,
                sentiment_score=0.26,
                raw_url=None,
            )
        )

    runtime = round(time.time() - started, 2)
    print(
        f"[SOLANA NAME INTEL] source_rows={len(source_rows)} "
        f"token_stats={len(token_stats)} "
        f"funny_candidates={len(funny_candidates)} "
        f"themes={len(theme_counter)} "
        f"returned={len(out)} "
        f"runtime={runtime}s"
    )

    return out
