#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — HYPERLIQUID UNIVERSE DISCOVERY
# ============================================================
#
# ████████╗ ██████╗ ██╗  ██╗███╗   ██╗ ██████╗██╗      █████╗ ██╗    ██╗
# ╚══██╔══╝██╔═══██╗██║ ██╔╝████╗  ██║██╔════╝██║     ██╔══██╗██║    ██║
#    ██║   ██║   ██║█████╔╝ ██╔██╗ ██║██║     ██║     ███████║██║ █╗ ██║
#    ██║   ██║   ██║██╔═██╗ ██║╚██╗██║██║     ██║     ██╔══██║██║███╗██║
#    ██║   ╚██████╔╝██║  ██╗██║ ╚████║╚██████╗███████╗██║  ██║╚███╔███╔╝
#    ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
#
# SYSTEM: ToknClaw Market Discovery
# MODULE: hyperliquid_universe_discovery
# PURPOSE:
# - Fetch all Hyperliquid perp markets from the public Info API
# - Fetch current mids for all available markets
# - Write a durable universe discovery artifact
# - Optionally add newly discovered markets to paper_candidates only
# - Never auto-promote assets to live trading
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Set


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

INFO_URL = "https://api.hyperliquid.xyz/info"

UNIVERSE_CONFIG_PATH = Path("/opt/toknclaw/config/trading_universe.json")
OUT_PATH = Path("/opt/toknclaw/data/analytics/hyperliquid_universe.json")
OUT_TMP_PATH = Path("/opt/toknclaw/data/analytics/hyperliquid_universe.tmp")


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

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


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path: Path, tmp_path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)

    tmp_path.replace(path)


def post_info(payload: Dict[str, Any], timeout: int = 20) -> Any:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        INFO_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ToknClaw/1.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw)


def enabled_assets_from_config(cfg: Dict[str, Any]) -> Set[str]:
    tiers = safe_dict(cfg.get("tiers"))
    enabled_tiers = safe_list(cfg.get("enabled_tiers"))

    assets: Set[str] = set()

    for tier in enabled_tiers:
        for asset in safe_list(tiers.get(tier)):
            asset = safe_upper(asset)
            if asset:
                assets.add(asset)

    return assets


def all_config_assets(cfg: Dict[str, Any]) -> Set[str]:
    tiers = safe_dict(cfg.get("tiers"))
    assets: Set[str] = set()

    for _, rows in tiers.items():
        for asset in safe_list(rows):
            asset = safe_upper(asset)
            if asset:
                assets.add(asset)

    return assets


def normalize_meta_universe(meta: Dict[str, Any], mids: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    universe = safe_list(meta.get("universe"))

    for idx, raw in enumerate(universe):
        row = safe_dict(raw)
        name = safe_upper(row.get("name"))

        if not name:
            continue

        mid = safe_float(mids.get(name), 0.0)

        rows.append({
            "asset_id": idx,
            "name": name,
            "mid": mid,
            "sz_decimals": safe_int(row.get("szDecimals"), 0),
            "max_leverage": safe_int(row.get("maxLeverage"), 0),
            "margin_table_id": row.get("marginTableId"),
            "only_isolated": bool(row.get("onlyIsolated", False)),
            "is_delisted": bool(row.get("isDelisted", False)),
            "raw": row,
        })

    rows.sort(key=lambda x: x["name"])
    return rows


def apply_to_trading_universe(discovery: Dict[str, Any]) -> Dict[str, Any]:
    cfg = safe_dict(read_json(UNIVERSE_CONFIG_PATH, {}))
    tiers = safe_dict(cfg.get("tiers"))

    majors = {safe_upper(x) for x in safe_list(tiers.get("majors"))}
    midcaps = {safe_upper(x) for x in safe_list(tiers.get("midcaps"))}
    paper_existing = {safe_upper(x) for x in safe_list(tiers.get("paper_candidates"))}

    discovered = {
        safe_upper(row.get("name"))
        for row in safe_list(discovery.get("markets"))
        if not bool(safe_dict(row).get("is_delisted"))
    }

    new_paper = sorted(discovered - majors - midcaps)
    combined_paper = sorted(paper_existing.union(new_paper))

    tiers["paper_candidates"] = combined_paper
    cfg["tiers"] = tiers

    cfg["enabled_tiers"] = [
        "majors",
        "midcaps",
        "paper_candidates",
    ]

    cfg["paper_trade_only_tiers"] = [
        "paper_candidates",
    ]

    policy = safe_dict(cfg.get("discovery_policy"))
    policy["enabled"] = True
    policy["paper_first"] = True
    policy["auto_add_to_tier"] = "paper_candidates"
    policy["auto_promote_to_live"] = False
    policy["promotion_required"] = True
    policy["last_hyperliquid_discovery_at"] = utc_now_iso()
    cfg["discovery_policy"] = policy

    tmp_path = UNIVERSE_CONFIG_PATH.with_suffix(".json.tmp")
    write_json_atomic(UNIVERSE_CONFIG_PATH, tmp_path, cfg)

    return {
        "updated": True,
        "paper_candidates_count": len(combined_paper),
        "new_paper_candidates_count": len(new_paper),
        "new_paper_candidates": new_paper,
    }


# ---------------------------------------------------
# CORE
# ---------------------------------------------------

def discover_hyperliquid_universe(apply: bool = False) -> Dict[str, Any]:
    started = time.time()

    meta = safe_dict(post_info({"type": "meta"}))
    mids = safe_dict(post_info({"type": "allMids"}))

    universe_cfg = safe_dict(read_json(UNIVERSE_CONFIG_PATH, {}))
    configured_assets = all_config_assets(universe_cfg)
    enabled_assets = enabled_assets_from_config(universe_cfg)

    markets = normalize_meta_universe(meta, mids)

    tradable_markets = [
        row for row in markets
        if not bool(row.get("is_delisted")) and safe_float(row.get("mid"), 0.0) > 0
    ]

    discovered_assets = {safe_upper(row.get("name")) for row in tradable_markets}
    new_assets = sorted(discovered_assets - configured_assets)

    payload = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "system": "ToknClaw",
        "module": "hyperliquid_universe_discovery",
        "source": "https://api.hyperliquid.xyz/info",
        "apply_requested": apply,
        "runtime_sec": round(time.time() - started, 4),
        "summary": {
            "meta_universe_count": len(markets),
            "tradable_market_count": len(tradable_markets),
            "configured_asset_count": len(configured_assets),
            "enabled_asset_count": len(enabled_assets),
            "new_asset_count": len(new_assets),
        },
        "new_assets": new_assets,
        "configured_assets": sorted(configured_assets),
        "enabled_assets": sorted(enabled_assets),
        "markets": markets,
    }

    if apply:
        payload["apply_result"] = apply_to_trading_universe(payload)
    else:
        payload["apply_result"] = {
            "updated": False,
            "reason": "run_with_--apply_to_add_new_assets_to_paper_candidates",
        }

    write_json_atomic(OUT_PATH, OUT_TMP_PATH, payload)

    return payload


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Discover Hyperliquid perp universe")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Add newly discovered Hyperliquid markets to paper_candidates only.",
    )

    args = parser.parse_args()

    result = discover_hyperliquid_universe(apply=args.apply)

    print(json.dumps({
        "generated_at": result.get("generated_at"),
        "summary": result.get("summary"),
        "new_assets": result.get("new_assets", [])[:100],
        "apply_result": result.get("apply_result"),
        "output": str(OUT_PATH),
    }, indent=2))


if __name__ == "__main__":
    main()
