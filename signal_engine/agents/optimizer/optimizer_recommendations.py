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
# MODULE: optimizer_recommendations
# PURPOSE: Convert bounded metrics into safe optimizer recommendations for
#          thresholds, sizing, and paper-candidate promotion.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This module is designed to:
• evaluate performance by signal family and confidence band
• generate bounded recommendations only
• avoid direct source-code mutation
• remain additive and OpenClaw agent ready
"""

from __future__ import annotations

from typing import Any, Dict, List


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_optimizer_recommendations(
    metrics: Dict[str, Any],
    optimizer_cfg: Dict[str, Any],
    paper_trading_cfg: Dict[str, Any],
    trading_universe_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    mins = safe_dict(optimizer_cfg.get("minimum_sample_sizes"))
    limits = safe_dict(optimizer_cfg.get("change_limits"))
    promo_cfg = safe_dict(optimizer_cfg.get("promotion_policy"))

    min_per_reason = safe_int(mins.get("per_reason", 8), 8)
    min_per_entity = safe_int(mins.get("per_entity", 8), 8)
    max_threshold_step = safe_float(limits.get("max_threshold_step", 0.03), 0.03)
    max_size_step_pct = safe_float(limits.get("max_size_step_pct", 0.15), 0.15)

    recs: List[Dict[str, Any]] = []

    overall = safe_dict(metrics.get("overall"))
    by_reason = safe_dict(metrics.get("by_reason"))
    by_entity = safe_dict(metrics.get("by_entity"))
    by_confidence_band = safe_dict(metrics.get("by_confidence_band"))

    overall_win_rate = safe_float(overall.get("win_rate", 0.0), 0.0)
    overall_expectancy = safe_float(overall.get("avg_realized_pnl_usd", 0.0), 0.0)

    # ---------------------------------------------------
    # THRESHOLD RECOMMENDATIONS
    # ---------------------------------------------------

    low_band = safe_dict(by_confidence_band.get("0.25-0.49"))
    high_band = safe_dict(by_confidence_band.get("0.50-0.74"))

    low_count = safe_int(low_band.get("count", 0), 0)
    high_count = safe_int(high_band.get("count", 0), 0)

    if low_count >= 10 and safe_float(low_band.get("avg_realized_pnl_usd", 0.0), 0.0) < 0:
        current = safe_float(paper_trading_cfg.get("min_confidence_bullish", 0.25), 0.25)
        proposed = round(current + max_threshold_step, 4)
        recs.append({
            "type": "threshold",
            "target_file": "/opt/toknclaw/config/paper_trading_engine.json",
            "field": "min_confidence_bullish",
            "current": current,
            "proposed": proposed,
            "reason": "Low-confidence bullish trades underperforming in recent sample.",
            "confidence": 0.72,
        })

    if high_count >= 10 and safe_float(high_band.get("avg_realized_pnl_usd", 0.0), 0.0) > 0:
        current = safe_float(paper_trading_cfg.get("confidence_size_multiplier_cap", 2.2), 2.2)
        proposed = round(current * (1.0 + max_size_step_pct), 4)
        recs.append({
            "type": "sizing",
            "target_file": "/opt/toknclaw/config/paper_trading_engine.json",
            "field": "confidence_size_multiplier_cap",
            "current": current,
            "proposed": proposed,
            "reason": "Higher-confidence trades are outperforming and may justify larger concentration.",
            "confidence": 0.70,
        })

    # ---------------------------------------------------
    # SIGNAL FAMILY RECOMMENDATIONS
    # ---------------------------------------------------

    for reason, bucket in by_reason.items():
        count = safe_int(bucket.get("count", 0), 0)
        expectancy = safe_float(bucket.get("avg_realized_pnl_usd", 0.0), 0.0)
        win_rate = safe_float(bucket.get("win_rate", 0.0), 0.0)

        if count < min_per_reason:
            continue

        if expectancy > 0 and win_rate >= max(overall_win_rate, 0.50):
            recs.append({
                "type": "weight_review",
                "target_file": "future:/opt/toknclaw/config/trade_signal_weights.json",
                "field": reason,
                "current": None,
                "proposed": "increase_small_step",
                "reason": f"Signal reason '{reason}' is outperforming recent baseline.",
                "confidence": 0.68,
            })

        elif expectancy < 0 and win_rate < overall_win_rate:
            recs.append({
                "type": "weight_review",
                "target_file": "future:/opt/toknclaw/config/trade_signal_weights.json",
                "field": reason,
                "current": None,
                "proposed": "decrease_small_step",
                "reason": f"Signal reason '{reason}' is underperforming recent baseline.",
                "confidence": 0.68,
            })

    # ---------------------------------------------------
    # ENTITY / PROMOTION RECOMMENDATIONS
    # ---------------------------------------------------

    if bool(promo_cfg.get("enabled", True)):
        minimum_paper_trades = safe_int(promo_cfg.get("minimum_paper_trades", 20), 20)
        minimum_win_rate = safe_float(promo_cfg.get("minimum_win_rate", 0.52), 0.52)
        minimum_expectancy = safe_float(promo_cfg.get("minimum_expectancy_usd", 0.0), 0.0)

        paper_candidates = safe_dict(trading_universe_cfg.get("tiers", {})).get("paper_candidates", [])
        paper_candidates = [clean_text(x).upper() for x in paper_candidates if clean_text(x)]

        for entity in paper_candidates:
            bucket = safe_dict(by_entity.get(entity))
            count = safe_int(bucket.get("count", 0), 0)
            win_rate = safe_float(bucket.get("win_rate", 0.0), 0.0)
            expectancy = safe_float(bucket.get("avg_realized_pnl_usd", 0.0), 0.0)

            if count >= minimum_paper_trades and win_rate >= minimum_win_rate and expectancy >= minimum_expectancy:
                recs.append({
                    "type": "promotion",
                    "target_file": "/opt/toknclaw/config/trading_universe.json",
                    "field": f"tiers.paper_candidates->{entity}",
                    "current": "paper_candidates",
                    "proposed": "promote_to_midcaps",
                    "reason": f"{entity} met paper-trading promotion thresholds.",
                    "confidence": 0.76,
                })

    # ---------------------------------------------------
    # PORTFOLIO RISK RECOMMENDATIONS
    # ---------------------------------------------------

    if overall_expectancy < 0 and safe_int(overall.get("count", 0), 0) >= 20:
        current = safe_float(paper_trading_cfg.get("base_position_size_usd", 250.0), 250.0)
        proposed = round(current * (1.0 - max_size_step_pct), 4)
        recs.append({
            "type": "risk",
            "target_file": "/opt/toknclaw/config/paper_trading_engine.json",
            "field": "base_position_size_usd",
            "current": current,
            "proposed": proposed,
            "reason": "Recent paper-trading expectancy is negative; reduce baseline risk.",
            "confidence": 0.74,
        })

    return {
        "generated_at": metrics.get("generated_at"),
        "mode": clean_text(optimizer_cfg.get("mode", "recommend_only")),
        "count": len(recs),
        "recommendations": recs,
    }
