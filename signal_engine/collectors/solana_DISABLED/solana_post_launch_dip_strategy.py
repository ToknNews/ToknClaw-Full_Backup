#!/usr/bin/env python3
"""
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
# MODULE: solana_post_launch_dip_strategy
# PURPOSE: Score recently active Solana memecoins for post-launch dip-buy
#          setups using only signal-lake data.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This engine is signal-lake driven and intentionally avoids new RPC calls.
It is designed to be:
• lightweight
• agent-tunable
• broadcast-friendly
• strategy-ready
• scalable under RPC budget constraints

Primary Use Cases
-----------------
• identify dip-buy watchlist candidates
• frame profitable post-launch trade setups
• feed future backtesting / labeling
• give ToknNews structured trade commentary
• allow OpenClaw agents to tune thresholds over time

Inputs
------
Reads from:
• /opt/toknclaw/data/signal_lake.json

Signal types considered:
• solana_pumpfun_launch
• solana_pumpfun_activity
• solana_raydium_pool_init
• solana_liquidity_event
• solana_liquidity_depth
• solana_volume_velocity
• solana_memecoin_trending
• solana_memecoin_velocity
• solana_jupiter_swap
• solana_jupiter_swap_activity
• solana_thin_liquidity_alert
• solana_mev_activity
• solana_funny_name_candidate
• solana_token_name_detected
• solana_token_symbol_detected

Outputs
-------
Emits:
• solana_strategy_entry_dip_buy
• solana_strategy_watch_dip_buy
• solana_strategy_avoid_dip_buy
• solana_dip_strategy_summary

Agent Readiness
---------------
Agents should tune:
• /opt/toknclaw/config/solana_post_launch_dip_strategy.json

Author: TOKN Systems
"""

from __future__ import annotations

import re
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Dict, List, Set, Tuple

from signal_engine.collectors.registry import register_collector
from models.signal import Signal
from runtime_config import load_config
from signal_lake import load_signal_lake


CONFIG_FILE = "solana_post_launch_dip_strategy.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "lookback_signal_count": 5000,
    "max_tokens_scored": 120,
    "max_entry_signals": 12,
    "max_watch_signals": 12,
    "max_avoid_signals": 10,
    "entry_score_min": 6.0,
    "watch_score_min": 3.5,
    "avoid_score_max": 0.5,
    "min_launch_signals": 1,
    "min_liquidity_signals": 1,
    "entry_requires_recent_interest": True,
    "entry_requires_no_thin_liquidity": True,
    "early_entry_override_enabled": True,
    "early_entry_override_min_score": 5.25,
    "early_entry_override_min_combined_interest": 3,
    "early_entry_override_max_mev_hits": 2,
    "stablecoin_mints": [
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    ],
    "major_quote_mints": [
        "So11111111111111111111111111111111111111112",
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    ],
    "weights": {
        "solana_pumpfun_launch": 3.0,
        "solana_pumpfun_activity": 0.8,
        "solana_raydium_pool_init": 2.8,
        "solana_liquidity_event": 1.4,
        "solana_liquidity_depth": 1.2,
        "solana_volume_velocity": 2.0,
        "solana_memecoin_trending": 2.2,
        "solana_memecoin_velocity": 1.8,
        "solana_jupiter_swap": 0.7,
        "solana_jupiter_swap_activity": 0.9,
        "solana_funny_name_candidate": 0.3,
        "solana_token_name_detected": 0.2,
        "solana_token_symbol_detected": 0.1,
        "solana_thin_liquidity_alert": -2.5,
        "solana_mev_activity": -1.2,
    },
    "dip_logic": {
        "mev_penalty_threshold": 8,
        "thin_liquidity_penalty_threshold": 1,
        "require_recent_interest": True,
        "recent_interest_types": [
            "solana_memecoin_trending",
            "solana_memecoin_velocity",
            "solana_volume_velocity",
            "solana_jupiter_swap_activity",
            "solana_jupiter_swap",
        ],
        "liquidity_types": [
            "solana_raydium_pool_init",
            "solana_liquidity_event",
            "solana_liquidity_depth",
            "solana_jupiter_swap",
            "solana_jupiter_swap_activity",
        ],
        "launch_types": [
            "solana_pumpfun_launch",
        ],
    },
}

BASE58_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")


def utc_now() -> datetime:
    return datetime.now(UTC)


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def debug_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("debug", True))


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if debug_enabled(cfg):
        print(f"[SOLANA DIP STRATEGY] {message}")


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

    base_dip_logic = dict(DEFAULT_CONFIG["dip_logic"])
    user_dip_logic = cfg.get("dip_logic", {})
    if isinstance(user_dip_logic, dict):
        base_dip_logic.update(user_dip_logic)
    merged["dip_logic"] = base_dip_logic

    return merged


def object_rows_only(rows: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for row in rows or []:
        if isinstance(row, dict):
            out.append(row)

    return out


def is_probable_token_entity(entity: str) -> bool:
    entity = clean_text(entity)

    if not entity:
        return False

    blocked_prefixes = (
        "SOLANA",
        "RAYDIUM",
        "PUMPFUN",
        "JUPITER",
        "TOKEN_",
        "POOL_",
        "THEME_",
    )

    for p in blocked_prefixes:
        if entity.upper().startswith(p):
            return False

    if "/" in entity:
        return False

    return len(entity) >= 20


def sget(row: Dict[str, Any], key: str, default: Any = None) -> Any:
    if not isinstance(row, dict):
        return default
    return row.get(key, default)


def parse_name_from_summary(summary: str, entity: str) -> str:
    summary = clean_text(summary)
    lower = summary.lower()

    markers = [
        "name candidate spotted:",
        "token name:",
        "name detected:",
        "resolved metadata:",
        "name=",
    ]

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


def unique_keep_order(values: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)

    return out


def extract_base58_candidates(text: str) -> List[str]:
    text = clean_text(text)
    if not text:
        return []
    return BASE58_RE.findall(text)


def extract_token_candidates_from_row(row: Dict[str, Any], cfg: Dict[str, Any]) -> List[str]:
    entity = clean_text(sget(row, "entity"))
    title = clean_text(sget(row, "title"))
    summary = clean_text(sget(row, "summary"))

    quote_mints = set(cfg.get("major_quote_mints", []))
    candidates: List[str] = []

    # direct token entity
    if is_probable_token_entity(entity):
        candidates.append(entity)

    # pair-style entity
    if " / " in entity:
        parts = [clean_text(x) for x in entity.split(" / ")]
        for part in parts:
            if is_probable_token_entity(part) and part not in quote_mints:
                candidates.append(part)

    # fallback: extract mint-looking substrings from title/summary
    for blob in [title, summary]:
        for match in extract_base58_candidates(blob):
            if is_probable_token_entity(match) and match not in quote_mints:
                candidates.append(match)

    return unique_keep_order(candidates)


def classify_token_rows(
    rows: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Tuple[List[Tuple[str, float]], Dict[str, Dict[str, Any]]]:
    weights = cfg.get("weights", {})
    dip_logic = cfg.get("dip_logic", {})

    recent_interest_types = {
        clean_text(x)
        for x in dip_logic.get("recent_interest_types", [])
        if clean_text(x)
    }
    liquidity_types = {
        clean_text(x)
        for x in dip_logic.get("liquidity_types", [])
        if clean_text(x)
    }
    launch_types = {
        clean_text(x)
        for x in dip_logic.get("launch_types", [])
        if clean_text(x)
    }

    token_map: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        signal_type = clean_text(sget(row, "signal_type"))
        summary = clean_text(sget(row, "summary"))
        title = clean_text(sget(row, "title"))

        candidate_tokens = extract_token_candidates_from_row(row, cfg)
        if not candidate_tokens:
            continue

        weight = float(weights.get(signal_type, 0.0))

        for entity in candidate_tokens:
            bucket = token_map.setdefault(
                entity,
                {
                    "token": entity,
                    "score": 0.0,
                    "signal_counts": Counter(),
                    "name": "",
                    "symbol": "",
                    "launch_hits": 0,
                    "liquidity_hits": 0,
                    "recent_interest_hits": 0,
                    "mev_hits": 0,
                    "thin_hits": 0,
                    "positive_hits": 0,
                    "negative_hits": 0,
                    "titles": [],
                    "summaries": [],
                    "entry_block_reasons": [],
                },
            )

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

            if signal_type in launch_types:
                bucket["launch_hits"] += 1

            if signal_type in liquidity_types:
                bucket["liquidity_hits"] += 1

            if signal_type in recent_interest_types:
                bucket["recent_interest_hits"] += 1

            if signal_type == "solana_mev_activity":
                bucket["mev_hits"] += 1

            if signal_type == "solana_thin_liquidity_alert":
                bucket["thin_hits"] += 1

            if signal_type == "solana_token_name_detected" and not bucket["name"]:
                bucket["name"] = parse_name_from_summary(summary, entity)

            if signal_type == "solana_token_symbol_detected" and not bucket["symbol"]:
                bucket["symbol"] = parse_symbol_from_summary(summary)

            if signal_type == "solana_funny_name_candidate" and not bucket["name"]:
                bucket["name"] = parse_name_from_summary(summary, entity)

    mev_penalty_threshold = int(dip_logic.get("mev_penalty_threshold", 8))
    thin_penalty_threshold = int(dip_logic.get("thin_liquidity_penalty_threshold", 1))
    require_recent_interest = bool(dip_logic.get("require_recent_interest", True))

    for token, bucket in token_map.items():
        bucket["entry_block_reasons"] = []

        if bucket["mev_hits"] >= mev_penalty_threshold:
            bucket["score"] -= 2.0
            bucket["entry_block_reasons"].append("mev_penalty")

        if bucket["thin_hits"] >= thin_penalty_threshold:
            bucket["score"] -= 2.0
            bucket["entry_block_reasons"].append("thin_liquidity_penalty")

        if require_recent_interest and bucket["recent_interest_hits"] == 0:
            bucket["score"] -= 1.5
            bucket["entry_block_reasons"].append("no_recent_interest")

        if bucket["launch_hits"] == 0:
            bucket["score"] -= 2.5
            bucket["entry_block_reasons"].append("no_launch_signal")

        if bucket["liquidity_hits"] == 0:
            bucket["score"] -= 2.0
            bucket["entry_block_reasons"].append("no_liquidity_signal")

        bucket["score"] = round(bucket["score"], 4)

    scored = sorted(
        [(token, meta["score"]) for token, meta in token_map.items()],
        key=lambda x: x[1],
        reverse=True,
    )

    max_tokens_scored = int(cfg.get("max_tokens_scored", 120))
    scored = scored[:max_tokens_scored]

    token_map = {token: token_map[token] for token, _ in scored}

    return scored, token_map


def display_name(meta: Dict[str, Any]) -> str:
    if clean_text(meta.get("name")):
        return clean_text(meta.get("name"))
    if clean_text(meta.get("symbol")):
        return clean_text(meta.get("symbol"))
    return clean_text(meta.get("token"))


def build_reason_list(meta: Dict[str, Any]) -> List[str]:
    counts: Counter = meta.get("signal_counts", Counter())
    reasons: List[str] = []

    if counts.get("solana_pumpfun_launch", 0) > 0:
        reasons.append(f"fresh launch x{counts['solana_pumpfun_launch']}")
    if counts.get("solana_raydium_pool_init", 0) > 0:
        reasons.append(f"pool init x{counts['solana_raydium_pool_init']}")
    if counts.get("solana_liquidity_event", 0) > 0:
        reasons.append(f"liquidity event x{counts['solana_liquidity_event']}")
    if counts.get("solana_liquidity_depth", 0) > 0:
        reasons.append(f"depth x{counts['solana_liquidity_depth']}")
    if counts.get("solana_volume_velocity", 0) > 0:
        reasons.append(f"velocity x{counts['solana_volume_velocity']}")
    if counts.get("solana_memecoin_trending", 0) > 0:
        reasons.append(f"trending x{counts['solana_memecoin_trending']}")
    if counts.get("solana_memecoin_velocity", 0) > 0:
        reasons.append(f"rank momentum x{counts['solana_memecoin_velocity']}")
    if counts.get("solana_jupiter_swap_activity", 0) > 0:
        reasons.append(f"swap activity x{counts['solana_jupiter_swap_activity']}")
    if counts.get("solana_jupiter_swap", 0) > 0:
        reasons.append(f"swaps x{counts['solana_jupiter_swap']}")
    if meta.get("thin_hits", 0) > 0:
        reasons.append(f"thin liquidity x{meta['thin_hits']}")
    if meta.get("mev_hits", 0) > 0:
        reasons.append(f"mev x{meta['mev_hits']}")

    return reasons[:6]


def qualifies_for_entry(meta: Dict[str, Any], score: float, cfg: Dict[str, Any]) -> bool:
    entry_score_min = float(cfg.get("entry_score_min", 6.0))
    min_launch_signals = int(cfg.get("min_launch_signals", 1))
    min_liquidity_signals = int(cfg.get("min_liquidity_signals", 1))
    require_recent_interest = bool(cfg.get("entry_requires_recent_interest", True))
    require_no_thin = bool(cfg.get("entry_requires_no_thin_liquidity", True))

    if score >= entry_score_min:
        if int(meta.get("launch_hits", 0)) < min_launch_signals:
            return False
        if int(meta.get("liquidity_hits", 0)) < min_liquidity_signals:
            return False
        if require_recent_interest and int(meta.get("recent_interest_hits", 0)) == 0:
            return False
        if require_no_thin and int(meta.get("thin_hits", 0)) > 0:
            return False
        if int(meta.get("mev_hits", 0)) >= 3:
            return False
        return True

    if not bool(cfg.get("early_entry_override_enabled", True)):
        return False

    early_score_min = float(cfg.get("early_entry_override_min_score", 5.25))
    early_interest_min = int(cfg.get("early_entry_override_min_combined_interest", 3))
    early_mev_max = int(cfg.get("early_entry_override_max_mev_hits", 2))

    combined_interest = int(meta.get("launch_hits", 0)) + int(meta.get("liquidity_hits", 0)) + int(meta.get("recent_interest_hits", 0))

    if score < early_score_min:
        return False
    if int(meta.get("launch_hits", 0)) < 1:
        return False
    if combined_interest < early_interest_min:
        return False
    if require_no_thin and int(meta.get("thin_hits", 0)) > 0:
        return False
    if int(meta.get("mev_hits", 0)) > early_mev_max:
        return False

    return True


def build_entry_signals(
    scored: List[Tuple[str, float]],
    token_map: Dict[str, Dict[str, Any]],
    cfg: Dict[str, Any],
) -> List[Signal]:
    out: List[Signal] = []
    max_entry_signals = int(cfg.get("max_entry_signals", 12))

    for token, score in scored:
        if len(out) >= max_entry_signals:
            break

        meta = token_map[token]

        if not qualifies_for_entry(meta, score, cfg):
            continue

        reasons = build_reason_list(meta)

        out.append(
            Signal(
                timestamp=utc_now(),
                source="toknclaw",
                signal_type="solana_strategy_entry_dip_buy",
                entity=token,
                title="Solana dip-buy entry candidate",
                summary=(
                    f"{display_name(meta)} qualifies for dip-buy entry setup | "
                    f"score={score:.2f} | "
                    f"launch_hits={meta.get('launch_hits', 0)} | "
                    f"liquidity_hits={meta.get('liquidity_hits', 0)} | "
                    f"recent_interest_hits={meta.get('recent_interest_hits', 0)} | "
                    f"reasons={', '.join(reasons)}"
                ),
                confidence=0.82,
                sentiment_score=0.41,
                raw_url=None,
            )
        )

    return out


def build_watch_signals(
    scored: List[Tuple[str, float]],
    token_map: Dict[str, Dict[str, Any]],
    cfg: Dict[str, Any],
) -> List[Signal]:
    out: List[Signal] = []
    watch_score_min = float(cfg.get("watch_score_min", 3.5))
    max_watch_signals = int(cfg.get("max_watch_signals", 12))

    for token, score in scored:
        if len(out) >= max_watch_signals:
            break

        meta = token_map[token]

        if qualifies_for_entry(meta, score, cfg):
            continue
        if score < watch_score_min:
            continue

        reasons = build_reason_list(meta)
        block_reasons = meta.get("entry_block_reasons", [])[:4]

        out.append(
            Signal(
                timestamp=utc_now(),
                source="toknclaw",
                signal_type="solana_strategy_watch_dip_buy",
                entity=token,
                title="Solana dip-buy watch candidate",
                summary=(
                    f"{display_name(meta)} is on dip-buy watchlist | "
                    f"score={score:.2f} | "
                    f"launch_hits={meta.get('launch_hits', 0)} | "
                    f"liquidity_hits={meta.get('liquidity_hits', 0)} | "
                    f"recent_interest_hits={meta.get('recent_interest_hits', 0)} | "
                    f"reasons={', '.join(reasons)} | "
                    f"entry_blockers={', '.join(block_reasons) if block_reasons else 'none'}"
                ),
                confidence=0.74,
                sentiment_score=0.26,
                raw_url=None,
            )
        )

    return out


def build_avoid_signals(
    scored: List[Tuple[str, float]],
    token_map: Dict[str, Dict[str, Any]],
    cfg: Dict[str, Any],
) -> List[Signal]:
    out: List[Signal] = []
    avoid_score_max = float(cfg.get("avoid_score_max", 0.5))
    max_avoid_signals = int(cfg.get("max_avoid_signals", 10))

    for token, score in reversed(scored):
        if len(out) >= max_avoid_signals:
            break

        meta = token_map[token]

        if score > avoid_score_max:
            continue

        reasons = build_reason_list(meta)

        out.append(
            Signal(
                timestamp=utc_now(),
                source="toknclaw",
                signal_type="solana_strategy_avoid_dip_buy",
                entity=token,
                title="Avoid Solana dip-buy setup",
                summary=(
                    f"{display_name(meta)} scores poorly for dip-buy setup | "
                    f"score={score:.2f} | "
                    f"launch_hits={meta.get('launch_hits', 0)} | "
                    f"liquidity_hits={meta.get('liquidity_hits', 0)} | "
                    f"recent_interest_hits={meta.get('recent_interest_hits', 0)} | "
                    f"reasons={', '.join(reasons)}"
                ),
                confidence=0.79,
                sentiment_score=-0.31,
                raw_url=None,
            )
        )

    return out


def build_summary_signal(
    scored: List[Tuple[str, float]],
    entry_rows: List[Signal],
    watch_rows: List[Signal],
    avoid_rows: List[Signal],
    token_map: Dict[str, Dict[str, Any]],
) -> List[Signal]:
    if not scored:
        return []

    top_tokens = []
    for token, score in scored[:5]:
        meta = token_map[token]
        top_tokens.append(f"{display_name(meta)}({score:.2f})")

    return [
        Signal(
            timestamp=utc_now(),
            source="toknclaw",
            signal_type="solana_dip_strategy_summary",
            entity="SOLANA_DIP_STRATEGY",
            title="Solana dip strategy summary",
            summary=(
                f"entries={len(entry_rows)} | "
                f"watch={len(watch_rows)} | "
                f"avoid={len(avoid_rows)} | "
                f"top={', '.join(top_tokens)}"
            ),
            confidence=0.77,
            sentiment_score=0.18,
            raw_url=None,
        )
    ]


@register_collector(
    name="solana_post_launch_dip_strategy",
    priority=2,
    tags=["solana", "strategy", "dip-buy", "broadcast", "agents"],
    category="onchain",
    execution="fast",
)
def fetch_solana_post_launch_dip_strategy_signals() -> List[Signal]:
    started = time.time()
    cfg = load_engine_config()
    signals: List[Signal] = []

    if not bool(cfg.get("enabled", True)):
        print("[SOLANA DIP STRATEGY] disabled by config")
        return signals

    lake = load_signal_lake()
    raw_rows = object_rows_only(lake.get("signals", []))

    lookback_signal_count = int(cfg.get("lookback_signal_count", 5000))
    rows = raw_rows[-lookback_signal_count:]

    scored, token_map = classify_token_rows(rows, cfg)

    if not scored:
        print("[SOLANA DIP STRATEGY] no scored tokens")
        return signals

    entry_rows = build_entry_signals(scored, token_map, cfg)
    watch_rows = build_watch_signals(scored, token_map, cfg)
    avoid_rows = build_avoid_signals(scored, token_map, cfg)
    summary_rows = build_summary_signal(scored, entry_rows, watch_rows, avoid_rows, token_map)

    signals.extend(entry_rows)
    signals.extend(watch_rows)
    signals.extend(avoid_rows)
    signals.extend(summary_rows)

    if debug_enabled(cfg):
        for token, score in scored[:10]:
            meta = token_map[token]
            debug_log(
                cfg,
                "token="
                + token
                + f" score={score:.2f}"
                + f" launch_hits={meta.get('launch_hits', 0)}"
                + f" liquidity_hits={meta.get('liquidity_hits', 0)}"
                + f" recent_interest_hits={meta.get('recent_interest_hits', 0)}"
                + f" thin_hits={meta.get('thin_hits', 0)}"
                + f" mev_hits={meta.get('mev_hits', 0)}"
            )

    runtime = round(time.time() - started, 2)
    print(
        f"[SOLANA DIP STRATEGY] rows={len(rows)} "
        f"tokens_scored={len(scored)} "
        f"entries={len(entry_rows)} "
        f"watch={len(watch_rows)} "
        f"avoid={len(avoid_rows)} "
        f"signals_returned={len(signals)} "
        f"runtime={runtime}s"
    )

    return signals
