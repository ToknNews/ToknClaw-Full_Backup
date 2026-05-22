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
# MODULE: quant_factor_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


EXPORT_DIR = Path("/opt/toknclaw/data/quant_factors")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _unique_preserve(items: List[Any]) -> List[Any]:
    seen = set()
    out = []

    for item in items:
        key = repr(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    return out


def _normalize_value(value: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return _clamp(value / scale)


def _now_ts() -> int:
    return int(time.time())


# -------------------------------------------------------
# Historical smoothing
# -------------------------------------------------------

def _load_previous_export() -> Dict[str, Any]:
    path = EXPORT_DIR / "latest_quant_factors.json"

    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _write_export(payload: Dict[str, Any]) -> None:
    latest = EXPORT_DIR / "latest_quant_factors.json"
    dated = EXPORT_DIR / f"quant_factors_{_now_ts()}.json"

    text = json.dumps(payload, indent=2)
    latest.write_text(text)
    dated.write_text(text)


def _previous_factor_map(previous: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = _safe_list(previous.get("rows"))
    out = {}

    for row in rows:
        row = _safe_dict(row)
        entity = str(row.get("entity") or "").upper()
        if entity:
            out[entity] = row

    return out


def _smooth_factor(current: float, previous: float | None, current_weight: float = 0.6, prev_weight: float = 0.4) -> float:
    if previous is None:
        return _clamp(current)
    return _clamp(current * current_weight + previous * prev_weight)


# -------------------------------------------------------
# Entity universe
# -------------------------------------------------------

def _collect_entities(snapshot: Dict[str, Any]) -> List[str]:
    entities: List[str] = []

    entity_intel = _safe_dict(snapshot.get("entity_intelligence"))
    entities.extend([str(k) for k in entity_intel.keys() if k])

    for cluster in _safe_list(snapshot.get("clusters")):
        cluster = _safe_dict(cluster)
        entity = cluster.get("entity")
        if entity:
            entities.append(str(entity))

    for corr in _safe_list(snapshot.get("narrative_correlations")):
        corr = _safe_dict(corr)
        entities.extend([str(e) for e in _safe_list(corr.get("entities")) if e])

    for narrative in _safe_list(snapshot.get("narratives")):
        narrative = _safe_dict(narrative)
        entities.extend([str(e) for e in _safe_list(narrative.get("entities")) if e])

    for signal in _safe_list(snapshot.get("signals")):
        signal = _safe_dict(signal)
        entity = signal.get("entity")
        if entity:
            entities.append(str(entity))

    return _unique_preserve([e.upper() for e in entities if str(e).strip()])


# -------------------------------------------------------
# Snapshot indexes
# -------------------------------------------------------

def _entity_intel_map(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    entity_intel = _safe_dict(snapshot.get("entity_intelligence"))
    return {str(k).upper(): _safe_dict(v) for k, v in entity_intel.items()}


def _entity_velocity_map(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    velocity = _safe_dict(snapshot.get("signal_velocity"))
    entities = _safe_list(velocity.get("entities"))

    out = {}
    for row in entities:
        row = _safe_dict(row)
        entity = str(row.get("entity") or "").upper()
        if entity:
            out[entity] = row
    return out


def _clusters_by_entity(snapshot: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}

    for cluster in _safe_list(snapshot.get("clusters")):
        cluster = _safe_dict(cluster)
        entity = str(cluster.get("entity") or "").upper()
        if not entity:
            continue
        out.setdefault(entity, []).append(cluster)

    return out


def _correlations_by_entity(snapshot: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}

    for corr in _safe_list(snapshot.get("narrative_correlations")):
        corr = _safe_dict(corr)
        for entity in _safe_list(corr.get("entities")):
            entity = str(entity).upper()
            if not entity:
                continue
            out.setdefault(entity, []).append(corr)

    return out


def _narratives_by_entity(snapshot: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}

    for narrative in _safe_list(snapshot.get("narratives")):
        narrative = _safe_dict(narrative)
        for entity in _safe_list(narrative.get("entities")):
            entity = str(entity).upper()
            if not entity:
                continue
            out.setdefault(entity, []).append(narrative)

    return out


def _signals_by_entity(snapshot: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}

    for signal in _safe_list(snapshot.get("signals")):
        signal = _safe_dict(signal)
        entity = str(signal.get("entity") or "").upper()
        if not entity:
            continue
        out.setdefault(entity, []).append(signal)

    return out


# -------------------------------------------------------
# Factor computations
# -------------------------------------------------------

def _momentum_factor(
    entity: str,
    entity_velocity: Dict[str, Dict[str, Any]],
    narratives_by_entity: Dict[str, List[Dict[str, Any]]],
) -> float:
    velocity_row = _safe_dict(entity_velocity.get(entity))
    entity_velocity_score = _safe_float(velocity_row.get("velocity_score"), 0.0)

    narratives = narratives_by_entity.get(entity, [])
    narrative_boost = 0.0

    for n in narratives:
        n = _safe_dict(n)
        narrative_boost += _safe_float(n.get("confidence"), 0.0) * 0.15

    return _clamp(entity_velocity_score + min(narrative_boost, 0.25))


def _liquidity_factor(
    entity: str,
    clusters_by_entity: Dict[str, List[Dict[str, Any]]],
    market_regime: Dict[str, Any],
) -> float:
    clusters = clusters_by_entity.get(entity, [])

    total_value = sum(_safe_float(c.get("total_value_usd"), 0.0) for c in clusters)
    base = _normalize_value(total_value, 10_000_000_000)

    liquidity_regime = str(market_regime.get("liquidity_regime") or "").lower()

    if liquidity_regime in {"capital_rotation", "institutional_flow"}:
        base += 0.10

    if any(str(c.get("cluster_type") or "") == "whale_activity" for c in clusters):
        base += 0.15

    return _clamp(base)


def _fundamentals_factor(
    entity: str,
    clusters_by_entity: Dict[str, List[Dict[str, Any]]],
    correlations_by_entity: Dict[str, List[Dict[str, Any]]],
) -> float:
    clusters = clusters_by_entity.get(entity, [])
    correlations = correlations_by_entity.get(entity, [])

    score = 0.0

    for c in clusters:
        c = _safe_dict(c)
        ctype = str(c.get("cluster_type") or "")
        value = _safe_float(c.get("total_value_usd"), 0.0)

        if ctype == "protocol_tvl":
            score += 0.25 + _normalize_value(value, 20_000_000_000) * 0.25
        elif ctype in {"protocol_revenue", "protocol_fees"}:
            score += 0.25 + _normalize_value(value, 1_000_000_000) * 0.25

    for corr in correlations:
        corr = _safe_dict(corr)
        ctype = str(corr.get("correlation_type") or "")

        if ctype in {"defi_capital_rotation", "protocol_fundamental_expansion"}:
            score += _safe_float(corr.get("confidence"), 0.0) * 0.20

    return _clamp(score)


def _speculation_factor(
    entity: str,
    clusters_by_entity: Dict[str, List[Dict[str, Any]]],
    correlations_by_entity: Dict[str, List[Dict[str, Any]]],
    retail_pulse: Dict[str, Any],
) -> float:
    clusters = clusters_by_entity.get(entity, [])
    correlations = correlations_by_entity.get(entity, [])

    score = 0.0

    if any(str(c.get("cluster_type") or "") == "retail_narrative" for c in clusters):
        score += 0.35

    for corr in correlations:
        corr = _safe_dict(corr)
        if str(corr.get("correlation_type") or "") == "risk_on_speculation_cycle":
            score += _safe_float(corr.get("confidence"), 0.0) * 0.35

    if bool(retail_pulse.get("memecoin_rotation")):
        score += 0.15

    if str(retail_pulse.get("retail_sentiment") or "").lower() == "risk_on":
        score += 0.15

    return _clamp(score)


def _stress_factor(
    entity: str,
    clusters_by_entity: Dict[str, List[Dict[str, Any]]],
    correlations_by_entity: Dict[str, List[Dict[str, Any]]],
    risks: Dict[str, Any],
    market_regime: Dict[str, Any],
) -> float:
    clusters = clusters_by_entity.get(entity, [])
    correlations = correlations_by_entity.get(entity, [])

    score = 0.0

    if any(str(c.get("cluster_type") or "") == "defi_liquidation" for c in clusters):
        score += 0.35

    for corr in correlations:
        corr = _safe_dict(corr)
        if str(corr.get("correlation_type") or "") == "market_stress_repricing":
            score += _safe_float(corr.get("confidence"), 0.0) * 0.40

    primary_risks = _safe_list(risks.get("primary"))
    if primary_risks:
        score += min(len(primary_risks) * 0.08, 0.20)

    if str(market_regime.get("liquidity_regime") or "").lower() == "liquidation_pressure":
        score += 0.20

    return _clamp(score)


def _policy_risk_factor(
    entity: str,
    clusters_by_entity: Dict[str, List[Dict[str, Any]]],
    cross_asset_intelligence: List[Dict[str, Any]],
) -> float:
    score = 0.0

    for relation in cross_asset_intelligence:
        relation = _safe_dict(relation)

        if entity not in [str(e).upper() for e in _safe_list(relation.get("entities"))]:
            continue

        if str(relation.get("relation_type") or "") == "crypto_policy_repricing":
            score += _safe_float(relation.get("confidence"), 0.0) * 0.50

    for c in clusters_by_entity.get(entity, []):
        c = _safe_dict(c)
        if str(c.get("cluster_type") or "") == "news_theme":
            score += 0.05

    return _clamp(score)


def _breadth_factor(
    entity: str,
    entity_intel: Dict[str, Dict[str, Any]],
    clusters_by_entity: Dict[str, List[Dict[str, Any]]],
    correlations_by_entity: Dict[str, List[Dict[str, Any]]],
    narratives_by_entity: Dict[str, List[Dict[str, Any]]],
) -> float:
    score = 0.0

    intel = _safe_dict(entity_intel.get(entity))
    score += min(_safe_float(intel.get("cluster_mentions"), 0.0) * 0.10, 0.30)
    score += min(len(clusters_by_entity.get(entity, [])) * 0.08, 0.25)
    score += min(len(correlations_by_entity.get(entity, [])) * 0.10, 0.25)
    score += min(len(narratives_by_entity.get(entity, [])) * 0.10, 0.20)

    return _clamp(score)


def _cross_asset_influence_factor(
    entity: str,
    cross_asset_intelligence: List[Dict[str, Any]],
) -> float:
    score = 0.0

    for relation in cross_asset_intelligence:
        relation = _safe_dict(relation)

        entities = [str(e).upper() for e in _safe_list(relation.get("entities"))]
        if entity not in entities:
            continue

        confidence = _safe_float(relation.get("confidence"), 0.0)
        relevance = str(relation.get("broadcast_relevance") or "").lower()

        score += confidence * 0.20
        if relevance == "high":
            score += 0.10

    return _clamp(score)


def _narrative_weight_factor(
    entity: str,
    narratives_by_entity: Dict[str, List[Dict[str, Any]]],
    correlations_by_entity: Dict[str, List[Dict[str, Any]]],
) -> float:
    score = 0.0

    for n in narratives_by_entity.get(entity, []):
        n = _safe_dict(n)
        score += _safe_float(n.get("confidence"), 0.0) * 0.15

    for c in correlations_by_entity.get(entity, []):
        c = _safe_dict(c)
        score += _safe_float(c.get("confidence"), 0.0) * 0.15

    return _clamp(score)


def _composite_factor(
    momentum: float,
    liquidity: float,
    fundamentals: float,
    speculation: float,
    stress: float,
    policy_risk: float,
    breadth: float,
    cross_asset_influence: float,
    narrative_weight: float,
) -> float:
    score = (
        momentum * 0.18 +
        liquidity * 0.16 +
        fundamentals * 0.18 +
        speculation * 0.10 +
        breadth * 0.12 +
        cross_asset_influence * 0.10 +
        narrative_weight * 0.10 -
        stress * 0.04 -
        policy_risk * 0.02
    )
    return _clamp(score)


# -------------------------------------------------------
# Classification / ranking / alerts
# -------------------------------------------------------

def _regime_bucket(composite: float, stress: float, speculation: float, fundamentals: float) -> str:
    if stress >= 0.65 and composite < 0.45:
        return "short_candidates"
    if composite >= 0.70 and fundamentals >= 0.45:
        return "long_candidates"
    if speculation >= 0.65 and composite >= 0.55:
        return "high_beta_watchlist"
    return "neutral"


def _build_sector_rankings(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    for row in rows:
        sectors = row.get("sectors") or ["unclassified"]
        for sector in sectors:
            grouped.setdefault(sector, []).append(row)

    ranked: Dict[str, List[Dict[str, Any]]] = {}

    for sector, sector_rows in grouped.items():
        sector_rows = sorted(
            sector_rows,
            key=lambda x: (
                x.get("composite_factor", 0.0),
                x.get("fundamentals_factor", 0.0),
                x.get("liquidity_factor", 0.0),
            ),
            reverse=True,
        )

        ranked[sector] = [
            {
                "entity": row["entity"],
                "composite_factor": row["composite_factor"],
                "fundamentals_factor": row["fundamentals_factor"],
                "liquidity_factor": row["liquidity_factor"],
            }
            for row in sector_rows[:10]
        ]

    return ranked


def _build_factor_alerts(
    rows: List[Dict[str, Any]],
    previous_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    alerts = []

    for row in rows:
        entity = row["entity"]
        previous = _safe_dict(previous_map.get(entity))

        if row["momentum_factor"] >= 0.80:
            alerts.append({
                "type": "momentum_spike",
                "entity": entity,
                "severity": "high",
                "title": f"{entity} momentum factor is elevated",
                "value": row["momentum_factor"],
            })

        if row["stress_factor"] >= 0.70:
            alerts.append({
                "type": "stress_risk",
                "entity": entity,
                "severity": "high",
                "title": f"{entity} stress factor is elevated",
                "value": row["stress_factor"],
            })

        if row["speculation_factor"] >= 0.75:
            alerts.append({
                "type": "speculation_spike",
                "entity": entity,
                "severity": "medium",
                "title": f"{entity} speculation factor is elevated",
                "value": row["speculation_factor"],
            })

        prev_comp = _safe_float(previous.get("composite_factor"), None)
        if prev_comp is not None:
            delta = row["composite_factor"] - prev_comp

            if delta >= 0.20:
                alerts.append({
                    "type": "composite_breakout",
                    "entity": entity,
                    "severity": "high",
                    "title": f"{entity} composite factor broke higher",
                    "value": round(delta, 2),
                })
            elif delta <= -0.20:
                alerts.append({
                    "type": "composite_breakdown",
                    "entity": entity,
                    "severity": "high",
                    "title": f"{entity} composite factor broke lower",
                    "value": round(delta, 2),
                })

    return alerts[:50]


def _build_regime_buckets(rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    buckets = {
        "long_candidates": [],
        "short_candidates": [],
        "high_beta_watchlist": [],
        "neutral": [],
    }

    for row in rows:
        buckets.setdefault(row["regime_bucket"], []).append(row["entity"])

    return buckets


def _build_endpoint_manifest() -> Dict[str, str]:
    return {
        "quant_factors": "/api/toknclaw/quant/factors",
        "quant_factor_summary": "/api/toknclaw/quant/factors/summary",
        "quant_factor_leaders": "/api/toknclaw/quant/factors/leaders",
        "quant_factor_alerts": "/api/toknclaw/quant/factors/alerts",
        "quant_factor_sector_rankings": "/api/toknclaw/quant/factors/sectors",
        "quant_factor_regime_buckets": "/api/toknclaw/quant/factors/regime-buckets",
    }


# -------------------------------------------------------
# Main public engine
# -------------------------------------------------------

def build_quant_factors(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    previous_export = _load_previous_export()
    previous_map = _previous_factor_map(previous_export)

    entities = _collect_entities(snapshot)

    entity_intel = _entity_intel_map(snapshot)
    entity_velocity = _entity_velocity_map(snapshot)
    clusters_by_entity = _clusters_by_entity(snapshot)
    correlations_by_entity = _correlations_by_entity(snapshot)
    narratives_by_entity = _narratives_by_entity(snapshot)
    signals_by_entity = _signals_by_entity(snapshot)

    market_regime = _safe_dict(snapshot.get("market_regime"))
    retail_pulse = _safe_dict(snapshot.get("retail_pulse"))
    risks = _safe_dict(snapshot.get("risks"))
    cross_asset_intelligence = _safe_list(snapshot.get("cross_asset_intelligence"))

    rows = []

    for entity in entities:
        raw_momentum = _momentum_factor(entity, entity_velocity, narratives_by_entity)
        raw_liquidity = _liquidity_factor(entity, clusters_by_entity, market_regime)
        raw_fundamentals = _fundamentals_factor(entity, clusters_by_entity, correlations_by_entity)
        raw_speculation = _speculation_factor(entity, clusters_by_entity, correlations_by_entity, retail_pulse)
        raw_stress = _stress_factor(entity, clusters_by_entity, correlations_by_entity, risks, market_regime)
        raw_policy_risk = _policy_risk_factor(entity, clusters_by_entity, cross_asset_intelligence)
        raw_breadth = _breadth_factor(entity, entity_intel, clusters_by_entity, correlations_by_entity, narratives_by_entity)
        raw_cross_asset = _cross_asset_influence_factor(entity, cross_asset_intelligence)
        raw_narrative_weight = _narrative_weight_factor(entity, narratives_by_entity, correlations_by_entity)

        previous = _safe_dict(previous_map.get(entity))

        momentum = _smooth_factor(raw_momentum, previous.get("momentum_factor"))
        liquidity = _smooth_factor(raw_liquidity, previous.get("liquidity_factor"))
        fundamentals = _smooth_factor(raw_fundamentals, previous.get("fundamentals_factor"))
        speculation = _smooth_factor(raw_speculation, previous.get("speculation_factor"))
        stress = _smooth_factor(raw_stress, previous.get("stress_factor"))
        policy_risk = _smooth_factor(raw_policy_risk, previous.get("policy_risk_factor"))
        breadth = _smooth_factor(raw_breadth, previous.get("breadth_factor"))
        cross_asset_influence = _smooth_factor(raw_cross_asset, previous.get("cross_asset_influence_factor"))
        narrative_weight = _smooth_factor(raw_narrative_weight, previous.get("narrative_weight_factor"))

        composite_raw = _composite_factor(
            momentum,
            liquidity,
            fundamentals,
            speculation,
            stress,
            policy_risk,
            breadth,
            cross_asset_influence,
            narrative_weight,
        )

        composite = _smooth_factor(composite_raw, previous.get("composite_factor"))

        sectors = _safe_list(_safe_dict(entity_intel.get(entity)).get("sectors"))
        sources = _safe_list(_safe_dict(entity_intel.get(entity)).get("supporting_sources"))
        urls = _safe_list(_safe_dict(entity_intel.get(entity)).get("supporting_urls"))

        if not sectors:
            for sig in signals_by_entity.get(entity, []):
                sig = _safe_dict(sig)
                sector = sig.get("sector")
                if sector:
                    sectors.append(sector)

        sectors = _unique_preserve(sectors)

        row = {
            "entity": entity,
            "momentum_factor": round(momentum, 2),
            "liquidity_factor": round(liquidity, 2),
            "fundamentals_factor": round(fundamentals, 2),
            "speculation_factor": round(speculation, 2),
            "stress_factor": round(stress, 2),
            "policy_risk_factor": round(policy_risk, 2),
            "breadth_factor": round(breadth, 2),
            "cross_asset_influence_factor": round(cross_asset_influence, 2),
            "narrative_weight_factor": round(narrative_weight, 2),
            "composite_factor": round(composite, 2),
            "regime_bucket": _regime_bucket(composite, stress, speculation, fundamentals),
            "sectors": sectors,
            "supporting_sources": sources,
            "supporting_urls": urls,
            "signal_count": len(signals_by_entity.get(entity, [])),
            "cluster_count": len(clusters_by_entity.get(entity, [])),
            "correlation_count": len(correlations_by_entity.get(entity, [])),
            "narrative_count": len(narratives_by_entity.get(entity, [])),
        }

        rows.append(row)

    rows.sort(
        key=lambda x: (
            x.get("composite_factor", 0.0),
            x.get("fundamentals_factor", 0.0),
            x.get("liquidity_factor", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )

    leaders = {
        "top_composite": rows[0]["entity"] if rows else None,
        "top_momentum": max(rows, key=lambda x: x.get("momentum_factor", 0.0))["entity"] if rows else None,
        "top_liquidity": max(rows, key=lambda x: x.get("liquidity_factor", 0.0))["entity"] if rows else None,
        "top_fundamentals": max(rows, key=lambda x: x.get("fundamentals_factor", 0.0))["entity"] if rows else None,
        "top_speculation": max(rows, key=lambda x: x.get("speculation_factor", 0.0))["entity"] if rows else None,
        "top_stress": max(rows, key=lambda x: x.get("stress_factor", 0.0))["entity"] if rows else None,
        "top_policy_risk": max(rows, key=lambda x: x.get("policy_risk_factor", 0.0))["entity"] if rows else None,
    }

    alerts = _build_factor_alerts(rows, previous_map)
    sector_rankings = _build_sector_rankings(rows)
    regime_buckets = _build_regime_buckets(rows)

    summary = {
        "entity_count": len(rows),
        "top_composite_entity": leaders["top_composite"],
        "top_composite_score": rows[0]["composite_factor"] if rows else 0.0,
        "avg_composite_score": round(sum(r["composite_factor"] for r in rows) / max(len(rows), 1), 2) if rows else 0.0,
        "avg_stress_factor": round(sum(r["stress_factor"] for r in rows) / max(len(rows), 1), 2) if rows else 0.0,
        "avg_speculation_factor": round(sum(r["speculation_factor"] for r in rows) / max(len(rows), 1), 2) if rows else 0.0,
        "alert_count": len(alerts),
        "long_candidate_count": len(regime_buckets["long_candidates"]),
        "short_candidate_count": len(regime_buckets["short_candidates"]),
        "high_beta_watchlist_count": len(regime_buckets["high_beta_watchlist"]),
    }

    payload = {
        "generated_at": _now_ts(),
        "rows": rows,
        "leaders": leaders,
        "summary": summary,
        "alerts": alerts,
        "sector_rankings": sector_rankings,
        "regime_buckets": regime_buckets,
        "endpoints": _build_endpoint_manifest(),
    }

    _write_export(payload)

    return payload
