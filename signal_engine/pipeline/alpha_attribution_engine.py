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
# MODULE: alpha_attribution_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
alpha_attribution_engine.py

ToknClaw Alpha Attribution Engine

Purpose
-------
Attribute predictive value across:
- trade signal directions
- quant factors
- regime buckets
- narrative types
- macro liquidity regime
- institutional flow regime

Outputs
-------
snapshot["alpha_attribution"]
snapshot["alpha_attribution_summary"]
snapshot["alpha_attribution_alerts"]
snapshot["alpha_attribution_components"]
snapshot["alpha_attribution_endpoints"]

Design
------
• future-proof
• factor / signal / regime attribution ready
• suitable for agents, dashboards, and later bot tuning
"""

from __future__ import annotations

from typing import Dict, List, Any
from collections import defaultdict


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


# -------------------------------------------------------
# Attribution builders
# -------------------------------------------------------

def _trade_direction_alpha(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = _safe_list(_safe_dict(snapshot.get("backtests")).get("trades"))

    grouped = defaultdict(list)

    for row in rows:
        row = _safe_dict(row)
        direction = _safe_str(row.get("direction"))
        if direction:
            grouped[direction].append(row)

    out = []
    for direction, items in grouped.items():
        count = len(items)
        avg_return = sum(_safe_float(x.get("return"), 0.0) for x in items) / max(count, 1)
        hit_rate = sum(1 for x in items if x.get("success")) / max(count, 1)

        out.append({
            "component_type": "trade_direction",
            "component": direction,
            "sample_count": count,
            "hit_rate": round(hit_rate, 3),
            "avg_return": round(avg_return, 4),
            "alpha_score": round((hit_rate * 0.6) + (avg_return * 0.4), 4),
        })

    return out


def _regime_bucket_alpha(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    quant_rows = _safe_list(snapshot.get("quant_factors"))
    backtest_rows = _safe_dict(snapshot.get("backtests")).get("trades", [])

    backtest_map = {}
    for row in _safe_list(backtest_rows):
        row = _safe_dict(row)
        entity = _safe_str(row.get("entity")).upper()
        if entity:
            backtest_map[entity] = row

    grouped = defaultdict(list)

    for row in quant_rows:
        row = _safe_dict(row)
        entity = _safe_str(row.get("entity")).upper()
        bucket = _safe_str(row.get("regime_bucket"))

        if not entity or not bucket or entity not in backtest_map:
            continue

        grouped[bucket].append(backtest_map[entity])

    out = []
    for bucket, items in grouped.items():
        count = len(items)
        avg_return = sum(_safe_float(x.get("return"), 0.0) for x in items) / max(count, 1)
        hit_rate = sum(1 for x in items if x.get("success")) / max(count, 1)

        out.append({
            "component_type": "regime_bucket",
            "component": bucket,
            "sample_count": count,
            "hit_rate": round(hit_rate, 3),
            "avg_return": round(avg_return, 4),
            "alpha_score": round((hit_rate * 0.6) + (avg_return * 0.4), 4),
        })

    return out


def _narrative_alpha(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    narrative_rows = _safe_list(_safe_dict(snapshot.get("backtests")).get("narratives"))

    grouped = defaultdict(list)

    for row in narrative_rows:
        row = _safe_dict(row)
        narrative = _safe_str(row.get("narrative"))
        if narrative:
            grouped[narrative].append(row)

    out = []
    for narrative, items in grouped.items():
        count = len(items)
        avg_return = sum(_safe_float(x.get("return"), 0.0) for x in items) / max(count, 1)

        out.append({
            "component_type": "narrative",
            "component": narrative,
            "sample_count": count,
            "avg_return": round(avg_return, 4),
            "alpha_score": round(avg_return, 4),
        })

    return out


def _macro_regime_alpha(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    regime = _safe_str(_safe_dict(snapshot.get("macro_liquidity_summary")).get("regime"))
    trade_metrics = _safe_dict(snapshot.get("backtest_summary"))

    if not regime:
        return []

    hit_rate = _safe_float(trade_metrics.get("hit_rate"), 0.0)
    avg_return = _safe_float(trade_metrics.get("avg_return"), 0.0)

    return [{
        "component_type": "macro_regime",
        "component": regime,
        "sample_count": _safe_float(trade_metrics.get("trade_count"), 0),
        "hit_rate": round(hit_rate, 3),
        "avg_return": round(avg_return, 4),
        "alpha_score": round((hit_rate * 0.6) + (avg_return * 0.4), 4),
    }]


def _institutional_regime_alpha(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    regime = _safe_str(_safe_dict(snapshot.get("institutional_flow_summary")).get("regime"))
    trade_metrics = _safe_dict(snapshot.get("backtest_summary"))

    if not regime:
        return []

    hit_rate = _safe_float(trade_metrics.get("hit_rate"), 0.0)
    avg_return = _safe_float(trade_metrics.get("avg_return"), 0.0)

    return [{
        "component_type": "institutional_regime",
        "component": regime,
        "sample_count": _safe_float(trade_metrics.get("trade_count"), 0),
        "hit_rate": round(hit_rate, 3),
        "avg_return": round(avg_return, 4),
        "alpha_score": round((hit_rate * 0.6) + (avg_return * 0.4), 4),
    }]


# -------------------------------------------------------
# Alerts / summary / endpoints
# -------------------------------------------------------

def _build_alerts(components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    alerts = []

    ranked = sorted(
        components,
        key=lambda x: _safe_float(x.get("alpha_score"), 0.0),
        reverse=True,
    )

    if ranked:
        top = ranked[0]
        if _safe_float(top.get("alpha_score"), 0.0) >= 0.55:
            alerts.append({
                "type": "strong_alpha_component",
                "severity": "medium",
                "component_type": top.get("component_type"),
                "component": top.get("component"),
                "title": f'{top.get("component")} is showing strong alpha contribution',
            })

    if ranked:
        bottom = ranked[-1]
        if _safe_float(bottom.get("alpha_score"), 0.0) <= 0.20:
            alerts.append({
                "type": "weak_alpha_component",
                "severity": "medium",
                "component_type": bottom.get("component_type"),
                "component": bottom.get("component"),
                "title": f'{bottom.get("component")} is showing weak alpha contribution',
            })

    return alerts[:25]


def _build_summary(components: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not components:
        return {
            "component_count": 0,
            "top_component": None,
            "top_alpha_score": 0.0,
            "alert_count": len(alerts),
        }

    ranked = sorted(
        components,
        key=lambda x: _safe_float(x.get("alpha_score"), 0.0),
        reverse=True,
    )

    top = ranked[0]

    return {
        "component_count": len(components),
        "top_component": top.get("component"),
        "top_component_type": top.get("component_type"),
        "top_alpha_score": top.get("alpha_score", 0.0),
        "alert_count": len(alerts),
    }


def _endpoint_manifest() -> Dict[str, str]:
    return {
        "alpha_attribution": "/api/toknclaw/alpha-attribution",
        "alpha_attribution_summary": "/api/toknclaw/alpha-attribution/summary",
        "alpha_attribution_alerts": "/api/toknclaw/alpha-attribution/alerts",
        "alpha_attribution_components": "/api/toknclaw/alpha-attribution/components",
    }


# -------------------------------------------------------
# Main engine
# -------------------------------------------------------

def build_alpha_attribution(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    components = []
    components.extend(_trade_direction_alpha(snapshot))
    components.extend(_regime_bucket_alpha(snapshot))
    components.extend(_narrative_alpha(snapshot))
    components.extend(_macro_regime_alpha(snapshot))
    components.extend(_institutional_regime_alpha(snapshot))

    components.sort(
        key=lambda x: (
            _safe_float(x.get("alpha_score"), 0.0),
            _safe_float(x.get("sample_count"), 0.0),
            _safe_str(x.get("component")),
        ),
        reverse=True,
    )

    alerts = _build_alerts(components)
    summary = _build_summary(components, alerts)

    return {
        "alpha_attribution": {
            "components": components,
        },
        "alpha_attribution_summary": summary,
        "alpha_attribution_alerts": alerts,
        "alpha_attribution_components": components,
        "alpha_attribution_endpoints": _endpoint_manifest(),
    }
