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
# MODULE: narrative_memory
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

from pipeline.narrative_storage import (
    load_active_history,
    load_archive_history,
    save_active_history,
    save_archive_history,
    prune_archive,
    archive_expired_narratives,
)


MICRO_WINDOW_SEC = 60 * 60
SESSION_WINDOW_SEC = 12 * 60 * 60
ACTIVE_WINDOW_SEC = 72 * 60 * 60
FADING_THRESHOLD_SEC = 6 * 60 * 60
EXPIRED_THRESHOLD_SEC = 24 * 60 * 60
ARCHIVE_THRESHOLD_SEC = 180 * 24 * 60 * 60


def _now_ts() -> int:
    return int(time.time())


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _strength_rank(strength: str) -> int:
    mapping = {
        "low": 1,
        "medium": 2,
        "high": 3,
        "dominant": 4,
    }
    return mapping.get(str(strength).lower(), 0)


def _bucket_age_sec(age_sec: int) -> str:
    if age_sec <= MICRO_WINDOW_SEC:
        return "micro"
    if age_sec <= SESSION_WINDOW_SEC:
        return "session"
    if age_sec <= ACTIVE_WINDOW_SEC:
        return "active"
    return "historical"


def _confidence_trend(prev_conf: float, new_conf: float) -> str:
    delta = round(new_conf - prev_conf, 3)

    if delta >= 0.05:
        return "rising"
    if delta <= -0.05:
        return "falling"
    return "stable"


def _compute_persistence_score(
    *,
    observation_count: int,
    first_seen: int,
    last_seen: int,
    now_ts: int,
) -> float:
    age = max(now_ts - first_seen, 1)
    recency = max(now_ts - last_seen, 0)

    observation_factor = min(observation_count / 8.0, 1.0)
    duration_factor = min(age / ACTIVE_WINDOW_SEC, 1.0)
    recency_penalty = min(recency / EXPIRED_THRESHOLD_SEC, 1.0)

    score = (0.5 * observation_factor) + (0.4 * duration_factor) - (0.25 * recency_penalty)
    return round(max(0.0, min(score, 1.0)), 2)


def _compute_velocity_score(
    *,
    observation_count: int,
    first_seen: int,
    last_seen: int,
) -> float:
    duration = max(last_seen - first_seen, 1)
    obs_per_hour = observation_count / (duration / 3600.0)
    normalized = min(obs_per_hour / 6.0, 1.0)
    return round(max(0.0, min(normalized, 1.0)), 2)


def _derive_state(
    *,
    last_seen: int,
    now_ts: int,
    observation_count: int,
    strength: str,
) -> str:
    inactivity = now_ts - last_seen

    if inactivity >= EXPIRED_THRESHOLD_SEC:
        return "expired"

    if inactivity >= FADING_THRESHOLD_SEC:
        return "fading"

    if _strength_rank(strength) >= 4 or observation_count >= 8:
        return "dominant"

    if observation_count >= 3 or _strength_rank(strength) >= 3:
        return "active"

    return "emerging"


def _memory_key(narrative: Dict[str, Any]) -> str:
    key = narrative.get("persistence_key")
    if key:
        return str(key)

    ntype = str(narrative.get("narrative_type") or "unknown")
    entities = sorted(str(e) for e in (narrative.get("entities") or []))
    return f"{ntype}::{'|'.join(entities)}"


def _merge_lists(old: List[Any], new: List[Any], limit: int = 12) -> List[Any]:
    out: List[Any] = []
    seen = set()

    for item in (old or []) + (new or []):
        rep = repr(item)
        if rep in seen:
            continue
        seen.add(rep)
        out.append(item)

    return out[:limit]


def _update_record(existing: Dict[str, Any], narrative: Dict[str, Any], now_ts: int) -> Dict[str, Any]:
    existing = _safe_dict(existing)
    narrative = _safe_dict(narrative)

    first_seen = int(existing.get("first_seen") or now_ts)
    last_seen = now_ts

    prev_conf = float(existing.get("latest_confidence") or 0.0)
    new_conf = float(narrative.get("confidence") or 0.0)

    observation_count = int(existing.get("observation_count") or 0) + 1
    peak_confidence = max(float(existing.get("peak_confidence") or 0.0), new_conf)

    strength = str(narrative.get("strength") or "low")
    state = _derive_state(
        last_seen=last_seen,
        now_ts=now_ts,
        observation_count=observation_count,
        strength=strength,
    )

    persistence_score = _compute_persistence_score(
        observation_count=observation_count,
        first_seen=first_seen,
        last_seen=last_seen,
        now_ts=now_ts,
    )

    velocity_score = _compute_velocity_score(
        observation_count=observation_count,
        first_seen=first_seen,
        last_seen=last_seen,
    )

    updated = {
        "memory_key": _memory_key(narrative),
        "narrative_type": narrative.get("narrative_type"),
        "title": narrative.get("title"),
        "summary": narrative.get("summary"),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "observation_count": observation_count,
        "peak_confidence": round(peak_confidence, 2),
        "latest_confidence": round(new_conf, 2),
        "previous_confidence": round(prev_conf, 2),
        "confidence_trend": _confidence_trend(prev_conf, new_conf),
        "strength": strength,
        "state": state,
        "persistence_score": persistence_score,
        "velocity_score": velocity_score,
        "age_bucket": _bucket_age_sec(now_ts - first_seen),
        "broadcast_relevance": narrative.get("broadcast_relevance"),
        "alert_relevance": narrative.get("alert_relevance"),
        "regime_alignment": narrative.get("regime_alignment"),
        "sector": narrative.get("sector"),
        "time_horizon": narrative.get("time_horizon"),
        "dominant_entities": _merge_lists(existing.get("dominant_entities") or [], narrative.get("entities") or [], limit=10),
        "supporting_cluster_ids": _merge_lists(existing.get("supporting_cluster_ids") or [], narrative.get("supporting_cluster_ids") or [], limit=20),
        "supporting_sources": _merge_lists(existing.get("supporting_sources") or [], narrative.get("supporting_sources") or [], limit=20),
        "supporting_urls": _merge_lists(existing.get("supporting_urls") or [], narrative.get("supporting_urls") or [], limit=20),
        "drivers": _merge_lists(existing.get("drivers") or [], narrative.get("drivers") or [], limit=12),
        "contradictions": _merge_lists(existing.get("contradictions") or [], narrative.get("contradictions") or [], limit=12),
        "latest_narrative_id": narrative.get("narrative_id"),
        "actionability": narrative.get("actionability"),
        "last_snapshot_attached": now_ts,
    }

    return updated


def _mark_inactive_records(active_store: Dict[str, Any], seen_keys: set[str], now_ts: int) -> Tuple[Dict[str, Any], List[str]]:
    active_store = _safe_dict(active_store)
    active_store.setdefault("narratives", {})

    expired_keys: List[str] = []

    for key, record in active_store["narratives"].items():
        if key in seen_keys:
            continue

        if not isinstance(record, dict):
            continue

        last_seen = int(record.get("last_seen") or 0)
        inactivity = now_ts - last_seen

        if inactivity >= EXPIRED_THRESHOLD_SEC:
            record["state"] = "expired"
            expired_keys.append(key)
        elif inactivity >= FADING_THRESHOLD_SEC:
            record["state"] = "fading"
        else:
            record["state"] = record.get("state") or "active"

        record["persistence_score"] = _compute_persistence_score(
            observation_count=int(record.get("observation_count") or 0),
            first_seen=int(record.get("first_seen") or now_ts),
            last_seen=last_seen,
            now_ts=now_ts,
        )

        record["age_bucket"] = _bucket_age_sec(max(now_ts - int(record.get("first_seen") or now_ts), 0))

    return active_store, expired_keys


def build_narrative_change_alerts(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    snapshot = _safe_dict(snapshot)
    history = _safe_list(snapshot.get("narrative_history"))

    alerts: List[Dict[str, Any]] = []

    for item in history:
        if not isinstance(item, dict):
            continue

        prev_conf = float(item.get("previous_confidence") or 0.0)
        latest_conf = float(item.get("latest_confidence") or 0.0)
        state = str(item.get("state") or "active")
        strength = str(item.get("strength") or "low")
        trend = str(item.get("confidence_trend") or "stable")
        observation_count = int(item.get("observation_count") or 0)
        persistence_score = float(item.get("persistence_score") or 0.0)

        change_type = None
        severity = "low"

        if state == "dominant" and observation_count >= 4:
            change_type = "newly_dominant"
            severity = "high"
        elif state == "fading":
            change_type = "fading"
            severity = "medium"
        elif trend == "rising" and (latest_conf - prev_conf) >= 0.05:
            change_type = "strengthening"
            severity = "high" if latest_conf >= 0.82 else "medium"
        elif trend == "falling" and (prev_conf - latest_conf) >= 0.05:
            change_type = "weakening"
            severity = "medium"
        elif observation_count >= 2 and persistence_score >= 0.45 and state in {"active", "dominant"}:
            change_type = "revived"
            severity = "medium"

        if not change_type:
            continue

        alerts.append({
            "memory_key": item.get("memory_key"),
            "narrative_type": item.get("narrative_type"),
            "title": item.get("title"),
            "change_type": change_type,
            "severity": severity,
            "state": state,
            "strength": strength,
            "latest_confidence": latest_conf,
            "previous_confidence": prev_conf,
            "confidence_trend": trend,
            "persistence_score": persistence_score,
            "velocity_score": float(item.get("velocity_score") or 0.0),
            "dominant_entities": item.get("dominant_entities") or [],
            "supporting_urls": item.get("supporting_urls") or [],
        })

    alerts.sort(
        key=lambda a: (
            a.get("severity") == "high",
            a.get("change_type") == "newly_dominant",
            a.get("latest_confidence", 0.0),
            a.get("persistence_score", 0.0),
            a.get("title", ""),
        ),
        reverse=True,
    )

    return alerts


def update_narrative_memory(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)
    narratives = _safe_list(snapshot.get("narratives"))
    now_ts = int(snapshot.get("timestamp") or _now_ts())

    active_store = load_active_history()
    archive_store = load_archive_history()

    active_store.setdefault("meta", {})
    active_store.setdefault("narratives", {})

    seen_keys: set[str] = set()

    for narrative in narratives:
        if not isinstance(narrative, dict):
            continue

        key = _memory_key(narrative)
        seen_keys.add(key)

        existing = active_store["narratives"].get(key, {})
        updated = _update_record(existing, narrative, now_ts)

        active_store["narratives"][key] = updated

        narrative["first_seen"] = updated["first_seen"]
        narrative["last_seen"] = updated["last_seen"]
        narrative["state"] = updated["state"]
        narrative["persistence_score"] = updated["persistence_score"]
        narrative["velocity_score"] = updated["velocity_score"]
        narrative["confidence_trend"] = updated["confidence_trend"]
        narrative["observation_count"] = updated["observation_count"]
        narrative["age_bucket"] = updated["age_bucket"]

    active_store, expired_keys = _mark_inactive_records(active_store, seen_keys, now_ts)
    active_store, archive_store = archive_expired_narratives(active_store, archive_store, expired_keys)
    archive_store = prune_archive(archive_store, now_ts=now_ts)

    active_store["meta"]["updated_at"] = now_ts
    active_store["meta"]["active_count"] = len(active_store["narratives"])
    archive_store["meta"]["updated_at"] = now_ts
    archive_store["meta"]["archive_count"] = len(archive_store["narratives"])

    save_active_history(active_store)
    save_archive_history(archive_store)

    active_records = list(active_store["narratives"].values())
    active_records.sort(
        key=lambda r: (
            r.get("state") == "dominant",
            r.get("state") == "active",
            r.get("persistence_score", 0.0),
            r.get("velocity_score", 0.0),
            r.get("latest_confidence", 0.0),
            r.get("title", ""),
        ),
        reverse=True,
    )

    snapshot["narrative_history"] = active_records
    snapshot["narrative_change_alerts"] = build_narrative_change_alerts({
        "narrative_history": active_records
    })
    snapshot["narrative_memory_meta"] = {
        "active_count": len(active_store["narratives"]),
        "archive_count": len(archive_store["narratives"]),
        "expired_this_cycle": len(expired_keys),
        "change_alert_count": len(snapshot["narrative_change_alerts"]),
        "retention_days": 180,
        "fading_threshold_sec": FADING_THRESHOLD_SEC,
        "expired_threshold_sec": EXPIRED_THRESHOLD_SEC,
        "active_window_sec": ACTIVE_WINDOW_SEC,
        "session_window_sec": SESSION_WINDOW_SEC,
        "micro_window_sec": MICRO_WINDOW_SEC,
    }

    return snapshot
