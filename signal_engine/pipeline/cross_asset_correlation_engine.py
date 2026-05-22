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
# MODULE: cross_asset_correlation_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

from typing import Any, Dict, List
from collections import defaultdict


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


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _relation_rows(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    rows.extend(_safe_list(snapshot.get("cross_asset_intelligence")))
    rows.extend(_safe_list(snapshot.get("narrative_correlations")))
    return [_safe_dict(x) for x in rows]


def _build_pairs(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    pairs = []

    for row in _relation_rows(snapshot):
        relation_type = _safe_str(row.get("relation_type") or row.get("correlation_type"))
        confidence = _safe_float(row.get("confidence"), 0.0)
        entities = [str(e).upper() for e in _safe_list(row.get("entities")) if str(e).strip()]

        if relation_type in {"crypto_macro_liquidity", "news_liquidity_repricing", "crypto_rates_pressure"}:
            pairs.append({
                "pair": "CRYPTO::MACRO",
                "relation_type": relation_type,
                "score": round(_clamp(confidence), 3),
                "entities": entities[:10],
            })

        if relation_type in {"crypto_risk_asset_alignment"}:
            pairs.append({
                "pair": "CRYPTO::EQUITIES",
                "relation_type": relation_type,
                "score": round(_clamp(confidence), 3),
                "entities": entities[:10],
            })

        if relation_type in {"crypto_commodity_inflation_link"}:
            pairs.append({
                "pair": "CRYPTO::COMMODITIES",
                "relation_type": relation_type,
                "score": round(_clamp(confidence), 3),
                "entities": entities[:10],
            })

        if relation_type in {"defi_capital_rotation", "institutional_accumulation"}:
            pairs.append({
                "pair": "CRYPTO::INTERNAL",
                "relation_type": relation_type,
                "score": round(_clamp(confidence), 3),
                "entities": entities[:10],
            })

        if relation_type in {"crypto_policy_repricing"}:
            pairs.append({
                "pair": "CRYPTO::POLICY",
                "relation_type": relation_type,
                "score": round(_clamp(confidence), 3),
                "entities": entities[:10],
            })

    return pairs


def _aggregate_pairs(pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped = defaultdict(lambda: {"score_sum": 0.0, "count": 0, "relation_types": [], "entities": []})

    for row in pairs:
        pair = row["pair"]
        grouped[pair]["score_sum"] += _safe_float(row.get("score"), 0.0)
        grouped[pair]["count"] += 1
        grouped[pair]["relation_types"].append(row.get("relation_type"))
        grouped[pair]["entities"].extend(row.get("entities") or [])

    out = []
    for pair, stats in grouped.items():
        avg_score = stats["score_sum"] / max(stats["count"], 1)

        out.append({
            "pair": pair,
            "correlation_score": round(avg_score, 3),
            "sample_count": stats["count"],
            "relation_types": sorted(set(stats["relation_types"])),
            "entities": sorted(set(stats["entities"]))[:15],
        })

    out.sort(key=lambda x: (x["correlation_score"], x["sample_count"], x["pair"]), reverse=True)
    return out


def _build_alerts(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    alerts = []

    for row in rows:
        if _safe_float(row.get("correlation_score"), 0.0) >= 0.75:
            alerts.append({
                "type": "high_cross_asset_correlation",
                "severity": "medium",
                "pair": row.get("pair"),
                "title": f'{row.get("pair")} correlation is elevated',
            })

    return alerts[:25]


def build_cross_asset_correlations(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    pairs = _build_pairs(snapshot)
    rows = _aggregate_pairs(pairs)
    alerts = _build_alerts(rows)

    summary = {
        "pair_count": len(rows),
        "top_pair": rows[0]["pair"] if rows else None,
        "top_score": rows[0]["correlation_score"] if rows else 0.0,
        "alert_count": len(alerts),
    }

    return {
        "cross_asset_correlations": rows,
        "cross_asset_correlation_summary": summary,
        "cross_asset_correlation_alerts": alerts,
        "cross_asset_correlation_endpoints": {
            "cross_asset_correlations": "/api/toknclaw/cross-asset-correlations",
            "cross_asset_correlation_summary": "/api/toknclaw/cross-asset-correlations/summary",
            "cross_asset_correlation_alerts": "/api/toknclaw/cross-asset-correlations/alerts",
        },
    }
