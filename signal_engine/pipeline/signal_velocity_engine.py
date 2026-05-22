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
# MODULE: signal_velocity_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


SNAPSHOT_DIR = Path("/opt/toknclaw/data/snapshots")
LOOKBACK_FILES = 24


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _load_recent_snapshots(limit: int = LOOKBACK_FILES) -> List[Dict[str, Any]]:
    if not SNAPSHOT_DIR.exists():
        return []

    files = sorted(
        [p for p in SNAPSHOT_DIR.glob("snapshot_*.json") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]

    out = []

    for path in reversed(files):
        try:
            out.append(json.loads(path.read_text()))
        except Exception:
            continue

    return out


def _velocity_bucket(score: float) -> str:
    if score >= 0.85:
        return "explosive"
    if score >= 0.65:
        return "fast"
    if score >= 0.40:
        return "building"
    return "slow"


def _entity_mentions_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, float]:
    entity_intel = _safe_dict(snapshot.get("entity_intelligence"))
    out: Dict[str, float] = {}

    for entity, record in entity_intel.items():
        r = _safe_dict(record)

        base = 1.0
        base += _safe_float(r.get("cluster_mentions"), 0.0) * 0.15
        base += _safe_float(r.get("latest_confidence"), 0.0)
        base += _safe_float(r.get("max_persistence_score"), 0.0) * 0.50

        out[str(entity).upper()] = round(base, 4)

    return out


def _correlation_mentions_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, float]:
    correlations = _safe_list(snapshot.get("narrative_correlations"))
    out: Dict[str, float] = {}

    for c in correlations:
        c = _safe_dict(c)

        ctype = str(c.get("correlation_type") or "")
        if not ctype:
            continue

        base = 1.0
        base += _safe_float(c.get("confidence"), 0.0)
        base += len(_safe_list(c.get("supporting_cluster_ids"))) * 0.10

        out[ctype] = out.get(ctype, 0.0) + round(base, 4)

    return out


def _cluster_mentions_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, float]:
    clusters = _safe_list(snapshot.get("clusters"))
    out: Dict[str, float] = {}

    for c in clusters:
        c = _safe_dict(c)

        cid = str(c.get("cluster_id") or "")
        if not cid:
            continue

        base = 1.0
        base += _safe_float(c.get("signal_count"), 0.0) * 0.20
        base += _safe_float(c.get("avg_confidence"), 0.0)
        base += min(_safe_float(c.get("total_value_usd"), 0.0) / 1_000_000_000, 3.0)

        out[cid] = round(base, 4)

    return out


def _narrative_mentions_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, float]:
    narratives = _safe_list(snapshot.get("narratives"))
    out: Dict[str, float] = {}

    for n in narratives:
        n = _safe_dict(n)

        ntype = str(n.get("narrative_type") or "")
        if not ntype:
            continue

        base = 1.0
        base += _safe_float(n.get("confidence"), 0.0)
        base += _safe_float(n.get("persistence_score"), 0.0) * 0.50
        base += _safe_float(n.get("velocity_score"), 0.0) * 0.50

        out[ntype] = out.get(ntype, 0.0) + round(base, 4)

    return out


def _regime_mentions_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, float]:
    market_regime = _safe_dict(snapshot.get("market_regime"))
    regime_name = str(market_regime.get("name") or "")
    if not regime_name:
        return {}

    return {
        regime_name: round(
            1.0 +
            _safe_float(market_regime.get("confidence"), 0.0) +
            len(_safe_list(market_regime.get("alerts"))) * 0.10,
            4
        )
    }


def _series_delta(hist: List[float]) -> tuple[float, float, float]:
    latest = hist[-1] if hist else 0.0
    prev_avg = sum(hist[:-1]) / max(len(hist[:-1]), 1) if len(hist) > 1 else 0.0
    delta = latest - prev_avg
    return latest, prev_avg, delta


def _compute_score(latest: float, prev_avg: float, baseline: float = 0.0) -> float:
    score = (latest - prev_avg + baseline) / 2.0
    return round(min(max(score, 0.0), 1.0), 2)


def _sector_priority_from_entity_rows(entity_rows: List[Dict[str, Any]]) -> List[str]:
    sector_scores: Dict[str, float] = {}

    for row in entity_rows[:15]:
        for sector in _safe_list(row.get("sectors")):
            sector_scores[sector] = sector_scores.get(sector, 0.0) + _safe_float(row.get("velocity_score"), 0.0)

    ranked = sorted(sector_scores.items(), key=lambda x: x[1], reverse=True)
    return [sector for sector, _ in ranked[:5]]


def _broadcast_urgency(top_entity_velocity: float, top_correlation_velocity: float, top_narrative_velocity: float, top_regime_velocity: float) -> str:
    peak = max(top_entity_velocity, top_correlation_velocity, top_narrative_velocity, top_regime_velocity)

    if peak >= 0.85:
        return "high"
    if peak >= 0.65:
        return "medium"
    return "low"


def _build_velocity_alerts(
    entity_rows: List[Dict[str, Any]],
    correlation_rows: List[Dict[str, Any]],
    cluster_rows: List[Dict[str, Any]],
    narrative_rows: List[Dict[str, Any]],
    regime_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    alerts: List[Dict[str, Any]] = []

    for row in entity_rows[:5]:
        if _safe_float(row.get("velocity_score"), 0.0) >= 0.85:
            alerts.append({
                "type": "entity_velocity_spike",
                "severity": "high",
                "entity": row.get("entity"),
                "title": f'{row.get("entity")} velocity spike detected',
                "velocity_score": row.get("velocity_score"),
            })

    for row in correlation_rows[:3]:
        if _safe_float(row.get("velocity_score"), 0.0) >= 0.80:
            alerts.append({
                "type": "correlation_acceleration",
                "severity": "high",
                "correlation_type": row.get("correlation_type"),
                "title": f'{row.get("correlation_type")} is accelerating',
                "velocity_score": row.get("velocity_score"),
            })

    for row in cluster_rows[:3]:
        if _safe_float(row.get("velocity_score"), 0.0) >= 0.80:
            alerts.append({
                "type": "cluster_breakout",
                "severity": "medium",
                "cluster_id": row.get("cluster_id"),
                "title": f'{row.get("cluster_id")} cluster is breaking out',
                "velocity_score": row.get("velocity_score"),
            })

    for row in narrative_rows[:3]:
        if _safe_float(row.get("velocity_score"), 0.0) >= 0.80:
            alerts.append({
                "type": "narrative_acceleration",
                "severity": "high",
                "narrative_type": row.get("narrative_type"),
                "title": f'{row.get("narrative_type")} narrative is accelerating',
                "velocity_score": row.get("velocity_score"),
            })

    for row in regime_rows[:1]:
        if _safe_float(row.get("velocity_score"), 0.0) >= 0.75:
            alerts.append({
                "type": "regime_shift_warning",
                "severity": "high",
                "regime": row.get("regime"),
                "title": f'{row.get("regime")} regime velocity is rising',
                "velocity_score": row.get("velocity_score"),
            })

    return alerts[:15]


def build_signal_velocity(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    recent = _load_recent_snapshots()

    current_entity_intel = _safe_dict(snapshot.get("entity_intelligence"))
    current_correlations = _safe_list(snapshot.get("narrative_correlations"))
    current_clusters = _safe_list(snapshot.get("clusters"))
    current_narratives = _safe_list(snapshot.get("narratives"))
    current_market_regime = _safe_dict(snapshot.get("market_regime"))

    entity_series: Dict[str, List[float]] = {}
    correlation_series: Dict[str, List[float]] = {}
    cluster_series: Dict[str, List[float]] = {}
    narrative_series: Dict[str, List[float]] = {}
    regime_series: Dict[str, List[float]] = {}

    for snap in recent:
        entity_map = _entity_mentions_from_snapshot(snap)
        corr_map = _correlation_mentions_from_snapshot(snap)
        cluster_map = _cluster_mentions_from_snapshot(snap)
        narrative_map = _narrative_mentions_from_snapshot(snap)
        regime_map = _regime_mentions_from_snapshot(snap)

        for entity, score in entity_map.items():
            entity_series.setdefault(entity, []).append(score)

        for ctype, score in corr_map.items():
            correlation_series.setdefault(ctype, []).append(score)

        for cid, score in cluster_map.items():
            cluster_series.setdefault(cid, []).append(score)

        for ntype, score in narrative_map.items():
            narrative_series.setdefault(ntype, []).append(score)

        for regime, score in regime_map.items():
            regime_series.setdefault(regime, []).append(score)

    entity_velocity = []
    for entity, record in current_entity_intel.items():
        hist = entity_series.get(str(entity).upper(), [])
        latest, prev_avg, delta = _series_delta(hist)

        score = _compute_score(
            latest,
            prev_avg,
            _safe_float(_safe_dict(record).get("max_velocity_score"), 0.0)
        )

        entity_velocity.append({
            "entity": entity,
            "velocity_score": score,
            "velocity_bucket": _velocity_bucket(score),
            "latest_signal_weight": round(latest, 2),
            "historical_avg_weight": round(prev_avg, 2),
            "delta_weight": round(delta, 2),
            "state": record.get("state"),
            "sectors": record.get("sectors") or [],
            "supporting_sources": record.get("supporting_sources") or [],
            "supporting_urls": record.get("supporting_urls") or [],
        })

    correlation_velocity = []
    for corr in current_correlations:
        corr = _safe_dict(corr)
        ctype = str(corr.get("correlation_type") or "")
        hist = correlation_series.get(ctype, [])
        latest, prev_avg, delta = _series_delta(hist)

        score = _compute_score(
            latest,
            prev_avg,
            _safe_float(corr.get("confidence"), 0.0)
        )

        correlation_velocity.append({
            "correlation_type": ctype,
            "velocity_score": score,
            "velocity_bucket": _velocity_bucket(score),
            "latest_signal_weight": round(latest, 2),
            "historical_avg_weight": round(prev_avg, 2),
            "delta_weight": round(delta, 2),
            "broadcast_relevance": corr.get("broadcast_relevance"),
            "supporting_cluster_ids": corr.get("supporting_cluster_ids") or [],
            "entities": corr.get("entities") or [],
        })

    cluster_velocity = []
    for cluster in current_clusters:
        cluster = _safe_dict(cluster)
        cid = str(cluster.get("cluster_id") or "")
        hist = cluster_series.get(cid, [])
        latest, prev_avg, delta = _series_delta(hist)

        score = _compute_score(
            latest,
            prev_avg,
            _safe_float(cluster.get("avg_confidence"), 0.0)
        )

        cluster_velocity.append({
            "cluster_id": cid,
            "cluster_type": cluster.get("cluster_type"),
            "entity": cluster.get("entity"),
            "velocity_score": score,
            "velocity_bucket": _velocity_bucket(score),
            "latest_signal_weight": round(latest, 2),
            "historical_avg_weight": round(prev_avg, 2),
            "delta_weight": round(delta, 2),
            "signal_count": cluster.get("signal_count"),
            "total_value_usd": cluster.get("total_value_usd"),
        })

    narrative_velocity = []
    for narrative in current_narratives:
        narrative = _safe_dict(narrative)
        ntype = str(narrative.get("narrative_type") or "")
        hist = narrative_series.get(ntype, [])
        latest, prev_avg, delta = _series_delta(hist)

        score = _compute_score(
            latest,
            prev_avg,
            _safe_float(narrative.get("confidence"), 0.0)
        )

        narrative_velocity.append({
            "narrative_type": ntype,
            "title": narrative.get("title"),
            "velocity_score": score,
            "velocity_bucket": _velocity_bucket(score),
            "latest_signal_weight": round(latest, 2),
            "historical_avg_weight": round(prev_avg, 2),
            "delta_weight": round(delta, 2),
            "sector": narrative.get("sector"),
            "entities": narrative.get("entities") or [],
            "broadcast_relevance": narrative.get("broadcast_relevance"),
        })

    regime_velocity = []
    regime_name = str(current_market_regime.get("name") or "")
    if regime_name:
        hist = regime_series.get(regime_name, [])
        latest, prev_avg, delta = _series_delta(hist)

        score = _compute_score(
            latest,
            prev_avg,
            _safe_float(current_market_regime.get("confidence"), 0.0)
        )

        regime_velocity.append({
            "regime": regime_name,
            "velocity_score": score,
            "velocity_bucket": _velocity_bucket(score),
            "latest_signal_weight": round(latest, 2),
            "historical_avg_weight": round(prev_avg, 2),
            "delta_weight": round(delta, 2),
            "broadcast_bias": current_market_regime.get("broadcast_bias"),
            "liquidity_regime": current_market_regime.get("liquidity_regime"),
        })

    entity_velocity.sort(
        key=lambda x: (
            x.get("velocity_score", 0.0),
            x.get("latest_signal_weight", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )

    correlation_velocity.sort(
        key=lambda x: (
            x.get("velocity_score", 0.0),
            x.get("latest_signal_weight", 0.0),
            x.get("correlation_type", ""),
        ),
        reverse=True,
    )

    cluster_velocity.sort(
        key=lambda x: (
            x.get("velocity_score", 0.0),
            _safe_float(x.get("total_value_usd"), 0.0),
            x.get("cluster_id", ""),
        ),
        reverse=True,
    )

    narrative_velocity.sort(
        key=lambda x: (
            x.get("velocity_score", 0.0),
            x.get("latest_signal_weight", 0.0),
            x.get("narrative_type", ""),
        ),
        reverse=True,
    )

    regime_velocity.sort(
        key=lambda x: (
            x.get("velocity_score", 0.0),
            x.get("latest_signal_weight", 0.0),
            x.get("regime", ""),
        ),
        reverse=True,
    )

    top_entity_velocity = entity_velocity[0]["velocity_score"] if entity_velocity else 0.0
    top_correlation_velocity = correlation_velocity[0]["velocity_score"] if correlation_velocity else 0.0
    top_narrative_velocity = narrative_velocity[0]["velocity_score"] if narrative_velocity else 0.0
    top_regime_velocity = regime_velocity[0]["velocity_score"] if regime_velocity else 0.0

    velocity_alerts = _build_velocity_alerts(
        entity_velocity,
        correlation_velocity,
        cluster_velocity,
        narrative_velocity,
        regime_velocity,
    )

    summary = {
        "top_entity": entity_velocity[0]["entity"] if entity_velocity else None,
        "top_entity_velocity": top_entity_velocity,
        "top_correlation": correlation_velocity[0]["correlation_type"] if correlation_velocity else None,
        "top_correlation_velocity": top_correlation_velocity,
        "top_cluster": cluster_velocity[0]["cluster_id"] if cluster_velocity else None,
        "top_cluster_velocity": cluster_velocity[0]["velocity_score"] if cluster_velocity else 0.0,
        "top_narrative": narrative_velocity[0]["narrative_type"] if narrative_velocity else None,
        "top_narrative_velocity": top_narrative_velocity,
        "top_regime": regime_velocity[0]["regime"] if regime_velocity else None,
        "top_regime_velocity": top_regime_velocity,
        "broadcast_urgency": _broadcast_urgency(
            top_entity_velocity,
            top_correlation_velocity,
            top_narrative_velocity,
            top_regime_velocity,
        ),
        "vertical_priority": _sector_priority_from_entity_rows(entity_velocity),
        "entity_count": len(entity_velocity),
        "correlation_count": len(correlation_velocity),
        "cluster_count": len(cluster_velocity),
        "narrative_count": len(narrative_velocity),
        "regime_count": len(regime_velocity),
        "alert_count": len(velocity_alerts),
    }

    return {
        "entities": entity_velocity,
        "correlations": correlation_velocity,
        "clusters": cluster_velocity,
        "narratives": narrative_velocity,
        "regimes": regime_velocity,
        "alerts": velocity_alerts,
        "summary": summary,
    }
