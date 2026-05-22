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
# MODULE: signal_outcome_price_enricher
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
Signal Outcome Price Enricher

Purpose
-------
Enrich tracked signal outcomes with price-aware forward performance data.

This module bridges:
• tracked signal lifecycle records
• local token price history
• return calculations
• win / loss labeling
• strategy evaluation inputs
• OpenClaw agent optimization loops

Responsibilities
----------------
• read tracked signal outcome records
• read local token price history
• find baseline price near signal time
• find forward prices for configured maturity windows
• compute forward return percentages
• compute simple outcome labels
• mark records priced / baseline_only / unpriced
• preserve atomic writes
• remain additive to ToknClaw without refactoring snapshot flow

Primary Inputs
--------------
/opt/toknclaw/data/signal_outcomes.json
/opt/toknclaw/data/token_price_history.json

Primary Output
--------------
/opt/toknclaw/data/signal_outcomes.json

Agent Readiness
---------------
OpenClaw agents should tune:
• /opt/toknclaw/config/signal_outcome_price_enricher.json

Author: TOKN Systems
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime_config import load_config


# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

CONFIG_FILE = "signal_outcome_price_enricher.json"

OUTCOMES_PATH = Path("/opt/toknclaw/data/signal_outcomes.json")
OUTCOMES_TMP_PATH = Path("/opt/toknclaw/data/signal_outcomes.tmp")

PRICE_HISTORY_PATH = Path("/opt/toknclaw/data/token_price_history.json")


# ---------------------------------------------------
# DEFAULT CONFIG
# ---------------------------------------------------

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "baseline_tolerance_minutes": 10,
    "forward_tolerance_minutes": 20,
    "win_threshold_pct": 5.0,
    "loss_threshold_pct": -5.0,
    "max_examples": 10,
}


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(UTC)


def now_iso() -> str:
    return utc_now().isoformat()


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return default


def debug_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("debug", True))


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if debug_enabled(cfg):
        print(f"[OUTCOME PRICE] {message}")


def parse_dt(value: Any) -> Optional[datetime]:
    text = clean_text(value)
    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)

        return dt.astimezone(UTC)

    except Exception:
        return None


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path: Path, tmp_path: Path, payload: Dict[str, Any]) -> None:
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2)

    tmp_path.replace(path)


def load_engine_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)

    if not isinstance(cfg, dict):
        return deepcopy(DEFAULT_CONFIG)

    merged = deepcopy(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def load_outcomes_store() -> Dict[str, Any]:
    data = read_json_file(
        OUTCOMES_PATH,
        {
            "updated_at": now_iso(),
            "schema_version": 1,
            "records": {},
            "summary": {},
        },
    )

    if not isinstance(data, dict):
        return {
            "updated_at": now_iso(),
            "schema_version": 1,
            "records": {},
            "summary": {},
        }

    if "records" not in data or not isinstance(data["records"], dict):
        data["records"] = {}

    if "summary" not in data or not isinstance(data["summary"], dict):
        data["summary"] = {}

    if "updated_at" not in data:
        data["updated_at"] = now_iso()

    return data


def load_price_history() -> Dict[str, Any]:
    data = read_json_file(
        PRICE_HISTORY_PATH,
        {
            "updated_at": now_iso(),
            "tokens": {},
        },
    )

    if not isinstance(data, dict):
        return {"updated_at": now_iso(), "tokens": {}}

    if "tokens" not in data or not isinstance(data["tokens"], dict):
        data["tokens"] = {}

    return data


# ---------------------------------------------------
# PRICE LOOKUP
# ---------------------------------------------------

def get_price_points_for_entity(entity: str, price_history: Dict[str, Any]) -> List[Dict[str, Any]]:
    tokens = price_history.get("tokens", {})
    if not isinstance(tokens, dict):
        return []

    rows = tokens.get(entity, [])
    if not isinstance(rows, list):
        return []

    out: List[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        ts = parse_dt(row.get("timestamp"))
        price_usd = safe_float(row.get("price_usd"), None)

        if ts is None or price_usd is None or price_usd <= 0:
            continue

        out.append(
            {
                "timestamp": ts,
                "price_usd": price_usd,
                "liquidity_usd": safe_float(row.get("liquidity_usd"), 0.0),
                "volume_24h": safe_float(row.get("volume_24h"), 0.0),
            }
        )

    out.sort(key=lambda x: x["timestamp"])
    return out


def find_nearest_price_around(
    points: List[Dict[str, Any]],
    target_dt: datetime,
    tolerance_minutes: int,
) -> Optional[Dict[str, Any]]:
    if not points:
        return None

    tolerance = timedelta(minutes=tolerance_minutes)
    best: Optional[Dict[str, Any]] = None

    for point in points:
        diff = abs(point["timestamp"] - target_dt)

        if diff > tolerance:
            continue

        if best is None or diff < abs(best["timestamp"] - target_dt):
            best = point

    return best


def find_nearest_price_at_or_after(
    points: List[Dict[str, Any]],
    target_dt: datetime,
    tolerance_minutes: int,
) -> Optional[Dict[str, Any]]:
    if not points:
        return None

    tolerance = timedelta(minutes=tolerance_minutes)
    best: Optional[Dict[str, Any]] = None

    for point in points:
        ts = point["timestamp"]

        if ts < target_dt:
            continue

        diff = ts - target_dt

        if diff > tolerance:
            continue

        if best is None or diff < (best["timestamp"] - target_dt):
            best = point

    return best


def compute_return_pct(baseline_price: float, forward_price: float) -> Optional[float]:
    if baseline_price <= 0:
        return None

    return ((forward_price - baseline_price) / baseline_price) * 100.0


def classify_return(return_pct: Optional[float], cfg: Dict[str, Any]) -> str:
    if return_pct is None:
        return "matured_unpriced"

    win_threshold = safe_float(cfg.get("win_threshold_pct"), 5.0)
    loss_threshold = safe_float(cfg.get("loss_threshold_pct"), -5.0)

    if return_pct >= win_threshold:
        return "win"

    if return_pct <= loss_threshold:
        return "loss"

    return "flat"


# ---------------------------------------------------
# RECORD ENRICHMENT
# ---------------------------------------------------

def ensure_window_payload_shape(payload: Dict[str, Any], minutes: int) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}

    payload.setdefault("minutes", minutes)
    payload.setdefault("matured", False)
    payload.setdefault("matured_at", None)
    payload.setdefault("price_available", False)
    payload.setdefault("baseline_price_usd", None)
    payload.setdefault("baseline_price_timestamp", None)
    payload.setdefault("forward_price_usd", None)
    payload.setdefault("forward_price_timestamp", None)
    payload.setdefault("forward_return_pct", None)
    payload.setdefault("max_favorable_excursion_pct", None)
    payload.setdefault("max_adverse_excursion_pct", None)
    payload.setdefault("label", "pending")

    return payload


def append_event(record: Dict[str, Any], event_type: str, note: str) -> None:
    events = record.setdefault("events", [])

    if not isinstance(events, list):
        record["events"] = []
        events = record["events"]

    events.append(
        {
            "ts": now_iso(),
            "type": clean_text(event_type),
            "note": clean_text(note),
        }
    )

    if len(events) > 50:
        record["events"] = events[-50:]


def enrich_record_with_prices(
    record: Dict[str, Any],
    price_history: Dict[str, Any],
    cfg: Dict[str, Any],
) -> None:
    signal_ts = parse_dt(record.get("signal_timestamp"))
    entity = clean_text(record.get("entity"))

    if signal_ts is None or not entity:
        record["price_status"] = "unpriced"
        record["updated_at"] = now_iso()
        return

    points = get_price_points_for_entity(entity, price_history)

    baseline_tolerance = safe_int(cfg.get("baseline_tolerance_minutes", 10), 10)
    forward_tolerance = safe_int(cfg.get("forward_tolerance_minutes", 20), 20)

    baseline_point = find_nearest_price_around(
        points=points,
        target_dt=signal_ts,
        tolerance_minutes=baseline_tolerance,
    )

    if baseline_point is not None:
        record["baseline_price_usd"] = baseline_point["price_usd"]
        record["baseline_price_timestamp"] = baseline_point["timestamp"].isoformat()
    else:
        record["baseline_price_usd"] = None
        record["baseline_price_timestamp"] = None

    maturity_status = record.get("maturity_status", {})
    if not isinstance(maturity_status, dict):
        maturity_status = {}
        record["maturity_status"] = maturity_status

    priced_any = False
    matured_any = False
    matured_unpriced_any = False
    labels_seen: List[str] = []

    for window_key, payload in list(maturity_status.items()):
        minutes = safe_int(
            payload.get("minutes") if isinstance(payload, dict) else window_key,
            0,
        )

        if minutes <= 0:
            continue

        payload = ensure_window_payload_shape(payload, minutes)
        maturity_status[window_key] = payload

        target_dt = signal_ts + timedelta(minutes=minutes)
        is_matured = utc_now() >= target_dt

        payload["matured"] = is_matured

        if is_matured and not payload.get("matured_at"):
            payload["matured_at"] = now_iso()

        if baseline_point is not None:
            payload["baseline_price_usd"] = baseline_point["price_usd"]
            payload["baseline_price_timestamp"] = baseline_point["timestamp"].isoformat()
        else:
            payload["baseline_price_usd"] = None
            payload["baseline_price_timestamp"] = None

        if not is_matured:
            payload["price_available"] = False
            payload["forward_price_usd"] = None
            payload["forward_price_timestamp"] = None
            payload["forward_return_pct"] = None
            payload["label"] = "pending"
            labels_seen.append("pending")
            continue

        matured_any = True

        if baseline_point is None:
            payload["price_available"] = False
            payload["forward_price_usd"] = None
            payload["forward_price_timestamp"] = None
            payload["forward_return_pct"] = None
            payload["label"] = "matured_unpriced"
            matured_unpriced_any = True
            labels_seen.append("matured_unpriced")
            continue

        forward_point = find_nearest_price_at_or_after(
            points=points,
            target_dt=target_dt,
            tolerance_minutes=forward_tolerance,
        )

        if forward_point is None:
            payload["price_available"] = False
            payload["forward_price_usd"] = None
            payload["forward_price_timestamp"] = None
            payload["forward_return_pct"] = None
            payload["label"] = "matured_unpriced"
            matured_unpriced_any = True
            labels_seen.append("matured_unpriced")
            continue

        return_pct = compute_return_pct(
            baseline_price=baseline_point["price_usd"],
            forward_price=forward_point["price_usd"],
        )

        payload["price_available"] = True
        payload["forward_price_usd"] = forward_point["price_usd"]
        payload["forward_price_timestamp"] = forward_point["timestamp"].isoformat()
        payload["forward_return_pct"] = return_pct
        payload["label"] = classify_return(return_pct, cfg)

        priced_any = True
        labels_seen.append(clean_text(payload["label"]))

    all_windows = [
        p for p in maturity_status.values()
        if isinstance(p, dict)
    ]

    if all_windows and all(bool(p.get("matured")) for p in all_windows):
        record["status"] = "matured"
    else:
        record["status"] = "pending"

    if priced_any:
        record["price_status"] = "priced"
    elif baseline_point is not None and matured_any:
        record["price_status"] = "baseline_only"
    elif baseline_point is not None:
        record["price_status"] = "baseline_found"
    else:
        record["price_status"] = "unpriced"

    if "win" in labels_seen:
        record["outcome_label"] = "win"
    elif "loss" in labels_seen:
        record["outcome_label"] = "loss"
    elif "flat" in labels_seen:
        record["outcome_label"] = "flat"
    elif matured_unpriced_any:
        record["outcome_label"] = "matured_unpriced"
    else:
        record["outcome_label"] = "pending"

    record["updated_at"] = now_iso()


# ---------------------------------------------------
# SUMMARY
# ---------------------------------------------------

def rebuild_summary(store: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    records = store.get("records", {})
    if not isinstance(records, dict):
        store["summary"] = {}
        return

    tracked_total = 0
    pending_total = 0
    matured_total = 0
    priced_total = 0
    matured_unpriced_total = 0
    skipped_total = 0
    wins_total = 0
    losses_total = 0
    flat_total = 0
    by_signal_type: Dict[str, int] = {}
    examples: List[Dict[str, Any]] = []

    max_examples = safe_int(cfg.get("max_examples", 10), 10)

    sortable = []
    for record_id, record in records.items():
        if not isinstance(record, dict):
            continue
        sortable.append((record_id, record))

    sortable.sort(
        key=lambda x: clean_text(x[1].get("updated_at")),
        reverse=True,
    )

    for record_id, record in sortable:
        tracked_total += 1

        signal_type = clean_text(record.get("signal_type"))
        by_signal_type[signal_type] = by_signal_type.get(signal_type, 0) + 1

        status = clean_text(record.get("status"))
        price_status = clean_text(record.get("price_status"))
        outcome_label = clean_text(record.get("outcome_label"))

        if status == "pending":
            pending_total += 1

        if status == "matured":
            matured_total += 1

        if status == "skipped":
            skipped_total += 1

        if price_status == "priced":
            priced_total += 1

        if outcome_label == "matured_unpriced":
            matured_unpriced_total += 1

        if outcome_label == "win":
            wins_total += 1

        if outcome_label == "loss":
            losses_total += 1

        if outcome_label == "flat":
            flat_total += 1

        if len(examples) < max_examples:
            examples.append(
                {
                    "record_id": record_id,
                    "signal_type": signal_type,
                    "entity": clean_text(record.get("entity")),
                    "status": status,
                    "price_status": price_status,
                    "outcome_label": outcome_label,
                    "signal_timestamp": clean_text(record.get("signal_timestamp")),
                    "baseline_price_usd": record.get("baseline_price_usd"),
                }
            )

    store["summary"] = {
        "tracked_total": tracked_total,
        "pending_total": pending_total,
        "matured_total": matured_total,
        "priced_total": priced_total,
        "matured_unpriced_total": matured_unpriced_total,
        "skipped_total": skipped_total,
        "wins_total": wins_total,
        "losses_total": losses_total,
        "flat_total": flat_total,
        "by_signal_type": by_signal_type,
        "examples": examples,
    }


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------

def run_enricher() -> Dict[str, Any]:
    cfg = load_engine_config()

    if not bool(cfg.get("enabled", True)):
        payload = load_outcomes_store()
        debug_log(cfg, "disabled by config")
        return payload

    store = load_outcomes_store()
    price_history = load_price_history()

    records = store.get("records", {})
    if not isinstance(records, dict):
        records = {}
        store["records"] = records

    debug_log(cfg, f"records_in_store={len(records)}")
    debug_log(cfg, f"tokens_in_price_history={len(price_history.get('tokens', {}))}")

    priced_records = 0
    baseline_records = 0

    for _, record in records.items():
        if not isinstance(record, dict):
            continue

        before_status = clean_text(record.get("price_status"))

        enrich_record_with_prices(
            record=record,
            price_history=price_history,
            cfg=cfg,
        )

        after_status = clean_text(record.get("price_status"))

        if after_status == "priced":
            priced_records += 1
        elif after_status in {"baseline_found", "baseline_only"}:
            baseline_records += 1

        if before_status != after_status:
            append_event(
                record,
                "price_enrichment_update",
                f"price_status changed from {before_status or 'none'} to {after_status or 'none'}",
            )

    rebuild_summary(store, cfg)

    store["updated_at"] = now_iso()
    store["schema_version"] = max(safe_int(store.get("schema_version", 1), 1), 2)

    write_json_atomic(OUTCOMES_PATH, OUTCOMES_TMP_PATH, store)

    summary = store.get("summary", {})

    debug_log(
        cfg,
        "tracked_total="
        + str(summary.get("tracked_total", 0))
        + " pending_total="
        + str(summary.get("pending_total", 0))
        + " matured_total="
        + str(summary.get("matured_total", 0))
        + " priced_total="
        + str(summary.get("priced_total", 0))
        + " wins_total="
        + str(summary.get("wins_total", 0))
        + " losses_total="
        + str(summary.get("losses_total", 0))
        + " flat_total="
        + str(summary.get("flat_total", 0))
    )

    debug_log(
        cfg,
        f"priced_records={priced_records} baseline_records={baseline_records}"
    )

    return store


def main() -> None:
    run_enricher()


if __name__ == "__main__":
    main()
