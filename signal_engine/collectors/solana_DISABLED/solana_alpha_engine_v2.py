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
# MODULE: solana_alpha_engine_v2
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
Solana Alpha Engine v2

Purpose
-------
Convert normalized Solana signals into per-token alpha scores.

Feeds
-----
• trading bot entry signals
• exit warnings
• broadcast insights
• research dashboards
• OpenClaw agents

Author: TOKN Systems
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from models.signal import Signal


CONFIG_PATH = Path("/opt/toknclaw/config/solana_alpha_weights.json")

DEFAULT_WEIGHTS = {
    "solana_token_mint": 1.5,
    "solana_mint_activity": 0.8,
    "solana_pumpfun_activity": 2.2,
    "solana_pumpfun_summary": 0.5,
    "solana_raydium_pool_init": 2.5,
    "solana_raydium_pool_activity": 0.8,
    "solana_liquidity_event": 1.8,
    "solana_jupiter_swap": 1.2,
    "solana_jupiter_swap_activity": 0.8,
    "solana_volume_velocity": 2.4,
    "solana_velocity_summary": 0.6,
    "solana_mev_activity": 1.0,
    "solana_liquidity_depth": 0.6,
    "solana_thin_liquidity_alert": -1.2,
    "solana_dev_wallet_sale": -3.0,
    "solana_holder_concentration_alert": -1.5,
}

STABLE_MINTS = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
}


def load_weights():
    if not CONFIG_PATH.exists():
        return DEFAULT_WEIGHTS, 4.0, -2.5

    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)

        weights = cfg.get("weights", DEFAULT_WEIGHTS)
        entry = cfg.get("entry_threshold", 4.0)
        exit_ = cfg.get("exit_threshold", -2.5)

        return weights, entry, exit_

    except Exception:
        return DEFAULT_WEIGHTS, 4.0, -2.5


def safe_get(signal: Any, field: str, default=None):
    if isinstance(signal, dict):
        return signal.get(field, default)
    return getattr(signal, field, default)


def extract_token(entity: str | None) -> str | None:
    if not entity:
        return None

    entity = str(entity).strip()

    if "/" in entity:
        parts = [p.strip() for p in entity.split("/") if p.strip()]

        pump_candidates = [p for p in parts if "pump" in p.lower()]
        if pump_candidates:
            return pump_candidates[0]

        non_stable = [p for p in parts if p not in STABLE_MINTS]
        if non_stable:
            return non_stable[0]

        return parts[0] if parts else None

    return entity


def build_alpha_scores(signals: List[Any]):
    weights, entry_threshold, exit_threshold = load_weights()

    token_scores: Dict[str, float] = {}
    token_reasons: Dict[str, List[str]] = {}

    for s in signals:
        stype = safe_get(s, "signal_type")
        entity = safe_get(s, "entity")

        token = extract_token(entity)
        if not token:
            continue

        weight = weights.get(stype)
        if weight is None:
            continue

        token_scores[token] = token_scores.get(token, 0.0) + weight
        token_reasons.setdefault(token, []).append(f"{stype}:{weight:+.2f}")

    return token_scores, token_reasons, entry_threshold, exit_threshold


def fetch_solana_alpha_signals(snapshot: Dict[str, Any]) -> List[Signal]:
    signals: List[Signal] = []

    raw_signals = snapshot.get("signals", [])

    scores, reasons, entry_threshold, exit_threshold = build_alpha_scores(raw_signals)

    now = datetime.utcnow()

    for token, score in scores.items():
        summary_reasons = ", ".join(reasons.get(token, [])[:6])

        if score >= entry_threshold:
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_alpha_entry_signal",
                    entity=token,
                    title="Solana Alpha Entry Signal",
                    summary=f"Alpha score {score:.2f} for {token}. Drivers: {summary_reasons}",
                    confidence=0.85,
                    sentiment_score=0.65,
                    raw_url=None,
                )
            )

        if score <= exit_threshold:
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_alpha_exit_signal",
                    entity=token,
                    title="Solana Alpha Exit Warning",
                    summary=f"Alpha score {score:.2f} indicates exit risk for {token}. Drivers: {summary_reasons}",
                    confidence=0.82,
                    sentiment_score=-0.65,
                    raw_url=None,
                )
            )

    if scores:
        top_tokens = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]

        signals.append(
            Signal(
                timestamp=now,
                source="toknclaw",
                signal_type="solana_alpha_summary",
                entity="SOLANA_ALPHA",
                title="Solana Alpha Summary",
                summary="Top tokens: " + ", ".join([f"{t[0]}({t[1]:.2f})" for t in top_tokens]),
                confidence=0.75,
                sentiment_score=0.30,
                raw_url=None,
            )
        )

    print(f"[SOLANA ALPHA V2] tokens={len(scores)} signals={len(signals)}")

    return signals
