#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — HYPERLIQUID MARKET QUALITY ENGINE
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
# MODULE: hyperliquid_market_quality_engine
# PURPOSE:
# - Fetch Hyperliquid L2 order book snapshots for relevant assets
# - Compute spread, depth, and book imbalance
# - Score whether a market is good/ok/thin/wide/unavailable
# - Produce a durable artifact for asset ranking and execution risk gates
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import requests

PROJECT_ROOT = Path("/opt/toknclaw")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from signal_engine.runtime_config import load_config


CONFIG_FILE = "hyperliquid_market_quality_engine.json"

INFO_URL = "https://api.hyperliquid.xyz/info"

SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot_trading.json")
STATE_PATH = Path("/opt/toknclaw/data/paper_trading_state.json")
RANKER_PATH = Path("/opt/toknclaw/data/analytics/asset_rotation_ranker.json")

OUTPUT_PATH = Path("/opt/toknclaw/data/analytics/hyperliquid_market_quality.json")
TMP_OUTPUT_PATH = Path("/opt/toknclaw/data/analytics/hyperliquid_market_quality.tmp")


DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,

    "request_timeout_sec": 8,
    "max_assets_per_run": 25,

    "depth_levels": 10,
    "min_depth_usd_good": 250000,
    "min_depth_usd_ok": 75000,

    "max_spread_bps_good": 8,
    "max_spread_bps_ok": 20,
    "max_spread_bps_tradeable": 30,

    "book_imbalance_good_abs": 0.12,

    "include_open_positions": True,
    "include_top_ranked_assets": True,
    "include_trade_signal_assets": True,
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def safe_str(value: Any) -> str:
    return str(value or "").strip()


def safe_upper(value: Any) -> str:
    return safe_str(value).upper()


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


def safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path: Path, tmp_path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    unique_tmp = tmp_path.with_name(
        f"{tmp_path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )

    with open(unique_tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    unique_tmp.replace(path)


def load_engine_config() -> Dict[str, Any]:
    raw = load_config(CONFIG_FILE)
    cfg = dict(DEFAULT_CONFIG)

    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                merged = dict(cfg[key])
                merged.update(value)
                cfg[key] = merged
            else:
                cfg[key] = value

    return cfg


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if safe_bool(cfg.get("debug"), True):
        print(f"[HL MARKET QUALITY] {message}", flush=True)


def post_info(payload: Dict[str, Any], timeout_sec: int) -> Any:
    response = requests.post(
        INFO_URL,
        json=payload,
        timeout=timeout_sec,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ToknClaw/1.0",
        },
    )

    if response.status_code != 200:
        raise RuntimeError(f"Hyperliquid info status={response.status_code} body={response.text[:200]}")

    return response.json()


def extract_levels(book: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    data = book

    if isinstance(book, dict):
        data = book.get("levels")

    if not isinstance(data, list) or len(data) < 2:
        return [], []

    bids = safe_list(data[0])
    asks = safe_list(data[1])

    return [safe_dict(x) for x in bids], [safe_dict(x) for x in asks]


def level_notional_usd(level: Dict[str, Any]) -> float:
    px = safe_float(level.get("px"), 0.0)
    sz = safe_float(level.get("sz"), 0.0)
    return px * sz


def depth_usd(levels: List[Dict[str, Any]], max_levels: int) -> float:
    total = 0.0

    for level in levels[:max_levels]:
        total += level_notional_usd(level)

    return round(total, 4)


def evaluate_quality(spread_bps: float, total_depth_usd: float, cfg: Dict[str, Any]) -> str:
    max_good = safe_float(cfg.get("max_spread_bps_good"), 8)
    max_ok = safe_float(cfg.get("max_spread_bps_ok"), 20)
    max_tradeable = safe_float(cfg.get("max_spread_bps_tradeable"), 30)

    min_good_depth = safe_float(cfg.get("min_depth_usd_good"), 250000)
    min_ok_depth = safe_float(cfg.get("min_depth_usd_ok"), 75000)

    if spread_bps <= max_good and total_depth_usd >= min_good_depth:
        return "good"

    if spread_bps <= max_ok and total_depth_usd >= min_ok_depth:
        return "ok"

    if spread_bps <= max_tradeable and total_depth_usd > 0:
        return "thin"

    return "wide_or_illiquid"


def quality_score(status: str, spread_bps: float, total_depth_usd: float, cfg: Dict[str, Any]) -> float:
    if status == "good":
        base = 1.0
    elif status == "ok":
        base = 0.75
    elif status == "thin":
        base = 0.45
    else:
        base = 0.15

    spread_penalty = min(spread_bps / max(safe_float(cfg.get("max_spread_bps_tradeable"), 30), 1.0), 1.0) * 0.25
    depth_bonus = min(total_depth_usd / max(safe_float(cfg.get("min_depth_usd_good"), 250000), 1.0), 1.0) * 0.15

    return round(max(0.0, min(1.0, base - spread_penalty + depth_bonus)), 6)


def assets_from_open_positions() -> Set[str]:
    state = safe_dict(read_json(STATE_PATH, {}))
    assets: Set[str] = set()

    for position in safe_dict(state.get("open_positions")).values():
        entity = safe_upper(safe_dict(position).get("entity"))
        if entity:
            assets.add(entity)

    return assets


def assets_from_ranker(cfg: Dict[str, Any]) -> Set[str]:
    ranker = safe_dict(read_json(RANKER_PATH, {}))
    assets: Set[str] = set()

    max_assets = safe_int(cfg.get("max_assets_per_run"), 25)

    for row in safe_list(ranker.get("rows"))[:max_assets]:
        entity = safe_upper(safe_dict(row).get("entity"))
        if entity:
            assets.add(entity)

    return assets


def assets_from_trade_signals(cfg: Dict[str, Any]) -> Set[str]:
    snapshot = safe_dict(read_json(SNAPSHOT_PATH, {}))
    assets: Set[str] = set()

    max_assets = safe_int(cfg.get("max_assets_per_run"), 25)

    for row in safe_list(safe_dict(snapshot.get("trade_signals")).get("rows"))[:max_assets]:
        entity = safe_upper(safe_dict(row).get("entity"))
        if entity:
            assets.add(entity)

    return assets


def add_unique_asset(rows: List[str], seen: Set[str], entity: Any) -> None:
    asset = safe_upper(entity)
    if not asset:
        return

    if asset in seen:
        return

    seen.add(asset)
    rows.append(asset)


def selected_assets(cfg: Dict[str, Any]) -> List[str]:
    """
    Select assets for L2 quality checks in priority order.

    Priority:
    1. Open positions
    2. Top asset rotation ranker rows, preserving rank order
    3. Current trade-signal rows, preserving trade priority order

    Do not alphabetically sort before truncating, because that causes the
    engine to check irrelevant early-alphabet assets instead of the assets
    the bot is actively considering.
    """

    max_assets = safe_int(cfg.get("max_assets_per_run"), 25)

    rows: List[str] = []
    seen: Set[str] = set()

    if safe_bool(cfg.get("include_open_positions"), True):
        state = safe_dict(read_json(STATE_PATH, {}))
        for position in safe_dict(state.get("open_positions")).values():
            add_unique_asset(rows, seen, safe_dict(position).get("entity"))

    if safe_bool(cfg.get("include_top_ranked_assets"), True):
        ranker = safe_dict(read_json(RANKER_PATH, {}))
        for row in safe_list(ranker.get("rows")):
            add_unique_asset(rows, seen, safe_dict(row).get("entity"))
            if len(rows) >= max_assets:
                return rows[:max_assets]

    if safe_bool(cfg.get("include_trade_signal_assets"), True):
        snapshot = safe_dict(read_json(SNAPSHOT_PATH, {}))
        for row in safe_list(safe_dict(snapshot.get("trade_signals")).get("rows")):
            add_unique_asset(rows, seen, safe_dict(row).get("entity"))
            if len(rows) >= max_assets:
                return rows[:max_assets]

    return rows[:max_assets]

def fetch_l2_book_quality(entity: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    timeout_sec = safe_int(cfg.get("request_timeout_sec"), 8)
    depth_levels = safe_int(cfg.get("depth_levels"), 10)

    try:
        book = post_info(
            {
                "type": "l2Book",
                "coin": entity,
            },
            timeout_sec=timeout_sec,
        )

        bids, asks = extract_levels(book)

        if not bids or not asks:
            return {
                "entity": entity,
                "ok": False,
                "status": "unavailable",
                "reason": "missing_book_sides",
            }

        best_bid = safe_float(bids[0].get("px"), 0.0)
        best_ask = safe_float(asks[0].get("px"), 0.0)

        if best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
            return {
                "entity": entity,
                "ok": False,
                "status": "unavailable",
                "reason": "invalid_best_bid_ask",
            }

        mid = (best_bid + best_ask) / 2.0
        spread_bps = ((best_ask - best_bid) / mid) * 10000.0 if mid > 0 else 999999.0

        bid_depth = depth_usd(bids, depth_levels)
        ask_depth = depth_usd(asks, depth_levels)
        total_depth = round(bid_depth + ask_depth, 4)

        imbalance = 0.0
        if total_depth > 0:
            imbalance = (bid_depth - ask_depth) / total_depth

        status = evaluate_quality(spread_bps, total_depth, cfg)
        score = quality_score(status, spread_bps, total_depth, cfg)

        return {
            "entity": entity,
            "ok": True,
            "status": status,
            "quality_score": score,
            "timestamp": utc_now_iso(),
            "best_bid": round(best_bid, 12),
            "best_ask": round(best_ask, 12),
            "mid": round(mid, 12),
            "spread_bps": round(spread_bps, 6),
            "bid_depth_usd": bid_depth,
            "ask_depth_usd": ask_depth,
            "total_depth_usd": total_depth,
            "book_imbalance": round(imbalance, 6),
            "depth_levels": depth_levels,
            "top_bid_size": safe_float(bids[0].get("sz"), 0.0),
            "top_ask_size": safe_float(asks[0].get("sz"), 0.0),
            "raw_level_count": {
                "bids": len(bids),
                "asks": len(asks),
            },
        }

    except Exception as exc:
        return {
            "entity": entity,
            "ok": False,
            "status": "unavailable",
            "reason": str(exc),
            "timestamp": utc_now_iso(),
        }


def build_hyperliquid_market_quality(write_output: bool = True) -> Dict[str, Any]:
    cfg = load_engine_config()

    if not safe_bool(cfg.get("enabled"), True):
        payload = {
            "schema_version": 1,
            "generated_at": utc_now_iso(),
            "enabled": False,
            "rows": [],
        }
        if write_output:
            write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, payload)
        return payload

    started = time.time()
    assets = selected_assets(cfg)

    rows = []
    for entity in assets:
        rows.append(fetch_l2_book_quality(entity, cfg))

    ok_rows = [row for row in rows if safe_bool(row.get("ok"), False)]

    payload = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "system": "ToknClaw",
        "module": "hyperliquid_market_quality_engine",
        "source": "hyperliquid_info_l2Book",
        "runtime_sec": round(time.time() - started, 4),
        "selected_assets": assets,
        "summary": {
            "asset_count": len(assets),
            "ok_count": len(ok_rows),
            "good_count": sum(1 for row in ok_rows if row.get("status") == "good"),
            "ok_status_count": sum(1 for row in ok_rows if row.get("status") == "ok"),
            "thin_count": sum(1 for row in ok_rows if row.get("status") == "thin"),
            "unavailable_count": len(rows) - len(ok_rows),
            "avg_spread_bps": round(
                sum(safe_float(row.get("spread_bps"), 0.0) for row in ok_rows) / len(ok_rows),
                6,
            ) if ok_rows else 0.0,
            "avg_quality_score": round(
                sum(safe_float(row.get("quality_score"), 0.0) for row in ok_rows) / len(ok_rows),
                6,
            ) if ok_rows else 0.0,
        },
        "rows": rows,
    }

    if write_output:
        write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, payload)

    debug_log(
        cfg,
        f"assets={len(assets)} ok={len(ok_rows)} "
        f"good={payload['summary']['good_count']} "
        f"thin={payload['summary']['thin_count']} "
        f"runtime={payload['runtime_sec']}"
    )

    return payload


def main() -> None:
    payload = build_hyperliquid_market_quality(write_output=True)

    print(json.dumps({
        "generated_at": payload.get("generated_at"),
        "runtime_sec": payload.get("runtime_sec"),
        "summary": payload.get("summary"),
        "rows": [
            {
                "entity": row.get("entity"),
                "status": row.get("status"),
                "quality_score": row.get("quality_score"),
                "spread_bps": row.get("spread_bps"),
                "bid_depth_usd": row.get("bid_depth_usd"),
                "ask_depth_usd": row.get("ask_depth_usd"),
                "book_imbalance": row.get("book_imbalance"),
                "reason": row.get("reason"),
            }
            for row in safe_list(payload.get("rows"))[:25]
        ],
        "output": str(OUTPUT_PATH),
    }, indent=2))


if __name__ == "__main__":
    main()
