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
# MODULE: open_interest_change
# PURPOSE: Track multi-venue perpetual open-interest changes over time and emit
#          position build / unwind / squeeze-build flow signals.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This collector is designed to:
• fetch current open interest from supported venues
• persist short rolling OI history locally
• compute percentage change over configurable windows
• emit rising / falling OI signals
• detect bullish / bearish squeeze-build conditions
• remain additive and OpenClaw agent ready

Primary Config
--------------
/opt/toknclaw/config/open_interest_change_collector.json

Primary Local State
-------------------
/opt/toknclaw/data/flow/open_interest_history.json

Primary Outputs
---------------
• perp_open_interest_change
• perp_open_interest_rising
• perp_open_interest_falling
• perp_bullish_squeeze_build
• perp_bearish_squeeze_build
• perp_open_interest_change_summary
"""

from __future__ import annotations

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

import json
import time
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

import requests

from signal_engine.collectors.registry import register_collector
from signal_engine.models.signal import Signal
from signal_engine.runtime_config import load_config


# ---------------------------------------------------
# PATHS / CONFIG
# ---------------------------------------------------

CONFIG_FILE = "open_interest_change_collector.json"

OI_HISTORY_PATH = Path("/opt/toknclaw/data/flow/open_interest_history.json")
OI_HISTORY_TMP_PATH = Path("/opt/toknclaw/data/flow/open_interest_history.tmp")

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "symbols": [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "BNBUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "LINKUSDT",
        "AVAXUSDT",
        "ARBUSDT",
        "OPUSDT",
        "INJUSDT",
        "PYTHUSDT",
        "JUPUSDT",
        "RNDRUSDT",
    ],
    "timeout": 10,
    "history_points_per_symbol": 120,
    "comparison_lookback_points": 1,
    "min_valid_oi": 0.0,
    "rising_threshold_pct": 2.5,
    "falling_threshold_pct": -2.5,
    "strong_rising_threshold_pct": 6.0,
    "strong_falling_threshold_pct": -6.0,
    "max_signals_per_run": 100,
    "summary_top_n": 8,
    "emit_neutral_change_rows": True,
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


def debug_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("debug", True))


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if debug_enabled(cfg):
        print(f"[OI CHANGE] {message}")


def info_log(message: str) -> None:
    print(f"[OI CHANGE] {message}")


def load_engine_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)

    if not isinstance(cfg, dict):
        return deepcopy(DEFAULT_CONFIG)

    merged = deepcopy(DEFAULT_CONFIG)
    merged.update(cfg)

    symbols = merged.get("symbols")
    if not isinstance(symbols, list):
        merged["symbols"] = deepcopy(DEFAULT_CONFIG["symbols"])
    else:
        merged["symbols"] = [clean_text(x).upper() for x in symbols if clean_text(x)]

    return merged


def base_asset(symbol: str) -> str:
    text = clean_text(symbol).upper()

    for suffix in ("USDT", "USDC", "BUSD", "USD"):
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[:-len(suffix)]

    return text


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

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    tmp_path.replace(path)


# ---------------------------------------------------
# VENUE FETCHERS (HETZNER-SAFE)
# ---------------------------------------------------

def fetch_okx_oi(cfg: Dict[str, Any]) -> Dict[str, float]:
    url = "https://www.okx.com/api/v5/public/open-interest"
    out: Dict[str, float] = {}

    for symbol in cfg["symbols"]:
        inst = symbol.replace("USDT", "-USDT-SWAP")

        try:
            r = requests.get(url, params={"instId": inst}, timeout=cfg.get("timeout", 10))

            if r.status_code != 200:
                continue

            data = r.json().get("data", [])
            if not isinstance(data, list) or not data:
                continue

            oi = safe_float(data[0].get("oi"), 0.0)
            out[symbol] = oi

        except Exception:
            continue

    return out


def fetch_hyperliquid_oi(cfg: Dict[str, Any]) -> Dict[str, float]:
    url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "meta"}

    try:
        r = requests.post(url, json=payload, timeout=cfg.get("timeout", 10))
        if r.status_code != 200:
            return {}

        data = r.json()
    except Exception:
        return {}

    out: Dict[str, float] = {}

    for asset in data.get("universe", []):
        symbol = clean_text(asset.get("name")).upper() + "USDT"

        if symbol not in cfg["symbols"]:
            continue

        oi = safe_float(asset.get("openInterest"), 0.0)
        out[symbol] = oi

    return out


# ---------------------------------------------------
# HISTORY
# ---------------------------------------------------

def load_history() -> Dict[str, Any]:
    data = read_json(
        OI_HISTORY_PATH,
        {
            "updated_at": None,
            "symbols": {},
        },
    )

    if not isinstance(data, dict):
        return {"updated_at": None, "symbols": {}}

    if not isinstance(data.get("symbols"), dict):
        data["symbols"] = {}

    return data


def append_history(
    history: Dict[str, Any],
    snapshot_oi: Dict[str, Dict[str, float]],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    symbols_bucket = history.setdefault("symbols", {})
    if not isinstance(symbols_bucket, dict):
        history["symbols"] = {}
        symbols_bucket = history["symbols"]

    max_points = safe_int(cfg.get("history_points_per_symbol", 120), 120)
    ts = now_iso()

    for symbol, venues in snapshot_oi.items():
        series = symbols_bucket.setdefault(symbol, [])
        if not isinstance(series, list):
            symbols_bucket[symbol] = []
            series = symbols_bucket[symbol]

        avg_oi = 0.0
        if venues:
            avg_oi = sum(venues.values()) / len(venues)

        series.append(
            {
                "timestamp": ts,
                "avg_oi": avg_oi,
                "venues": venues,
            }
        )

        if len(series) > max_points:
            symbols_bucket[symbol] = series[-max_points:]

    history["updated_at"] = ts
    return history


def prior_point(series: List[Dict[str, Any]], lookback_points: int) -> Optional[Dict[str, Any]]:
    if not isinstance(series, list):
        return None

    if len(series) <= lookback_points:
        return None

    idx = -(lookback_points + 1)
    try:
        row = series[idx]
        if isinstance(row, dict):
            return row
    except Exception:
        return None

    return None


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100.0


# ---------------------------------------------------
# SIGNAL BUILDERS
# ---------------------------------------------------

def build_change_signal(
    entity: str,
    current_oi: float,
    previous_oi: float,
    delta_pct: float,
    venues: Dict[str, float],
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="multi_venue",
        signal_type="perp_open_interest_change",
        entity=entity,
        title=f"{entity} open interest change",
        summary=(
            f"oi_change_pct={delta_pct:.4f} | "
            f"current_oi={current_oi:.2f} | "
            f"previous_oi={previous_oi:.2f} | "
            f"venues={venues}"
        ),
        confidence=0.88,
        sentiment_score=0.0,
        raw_url=None,
    )


def build_rising_signal(
    entity: str,
    current_oi: float,
    previous_oi: float,
    delta_pct: float,
    strong: bool,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_open_interest_rising",
        entity=entity,
        title=f"{entity} open interest rising",
        summary=(
            f"{entity} OI is rising | "
            f"oi_change_pct={delta_pct:.4f} | "
            f"current_oi={current_oi:.2f} | "
            f"previous_oi={previous_oi:.2f} | "
            f"strength={'strong' if strong else 'normal'}"
        ),
        confidence=0.84 if strong else 0.78,
        sentiment_score=0.08,
        raw_url=None,
    )


def build_falling_signal(
    entity: str,
    current_oi: float,
    previous_oi: float,
    delta_pct: float,
    strong: bool,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_open_interest_falling",
        entity=entity,
        title=f"{entity} open interest falling",
        summary=(
            f"{entity} OI is falling | "
            f"oi_change_pct={delta_pct:.4f} | "
            f"current_oi={current_oi:.2f} | "
            f"previous_oi={previous_oi:.2f} | "
            f"strength={'strong' if strong else 'normal'}"
        ),
        confidence=0.84 if strong else 0.78,
        sentiment_score=-0.04,
        raw_url=None,
    )


def build_bullish_squeeze_build_signal(
    entity: str,
    current_oi: float,
    previous_oi: float,
    delta_pct: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_bullish_squeeze_build",
        entity=entity,
        title=f"{entity} bullish squeeze build",
        summary=(
            f"{entity} shows rising OI into potentially bullish squeeze conditions | "
            f"oi_change_pct={delta_pct:.4f} | "
            f"current_oi={current_oi:.2f} | "
            f"previous_oi={previous_oi:.2f}"
        ),
        confidence=0.86,
        sentiment_score=0.22,
        raw_url=None,
    )


def build_bearish_squeeze_build_signal(
    entity: str,
    current_oi: float,
    previous_oi: float,
    delta_pct: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_bearish_squeeze_build",
        entity=entity,
        title=f"{entity} bearish squeeze build",
        summary=(
            f"{entity} shows falling or stressed positioning consistent with bearish squeeze/liquidation risk | "
            f"oi_change_pct={delta_pct:.4f} | "
            f"current_oi={current_oi:.2f} | "
            f"previous_oi={previous_oi:.2f}"
        ),
        confidence=0.82,
        sentiment_score=-0.22,
        raw_url=None,
    )


def build_summary_signal(
    rows: List[Dict[str, Any]],
    rising_count: int,
    falling_count: int,
    bullish_squeeze_count: int,
    bearish_squeeze_count: int,
    summary_top_n: int,
) -> Signal:
    ranked = sorted(rows, key=lambda x: abs(safe_float(x.get("delta_pct"), 0.0)), reverse=True)

    top_parts: List[str] = []
    for row in ranked[:summary_top_n]:
        top_parts.append(f"{row['entity']}({row['delta_pct']:.2f}%)")

    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_open_interest_change_summary",
        entity="PERP_OI_CHANGE",
        title="Perpetual open interest change summary",
        summary=(
            f"rows={len(rows)} | "
            f"rising={rising_count} | "
            f"falling={falling_count} | "
            f"bullish_squeeze_build={bullish_squeeze_count} | "
            f"bearish_squeeze_build={bearish_squeeze_count} | "
            f"top_changes={', '.join(top_parts) if top_parts else 'none'}"
        ),
        confidence=0.84,
        sentiment_score=0.0,
        raw_url=None,
    )


# ---------------------------------------------------
# MAIN COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="open_interest_change",
    priority=1,
    tags=["flows", "perps", "oi", "change", "squeeze"],
    category="flows",
    execution="fast",
)
def fetch_open_interest_change_signals() -> List[Signal]:
    started = time.time()
    cfg = load_engine_config()
    signals: List[Signal] = []

    if not bool(cfg.get("enabled", True)):
        info_log("disabled by config")
        return signals

    okx = fetch_okx_oi(cfg)
    hyper = fetch_hyperliquid_oi(cfg)

    current_snapshot: Dict[str, Dict[str, float]] = {}

    for symbol in cfg["symbols"]:
        venues: Dict[str, float] = {}

        if symbol in okx:
            venues["okx"] = okx[symbol]

        if symbol in hyper:
            venues["hyperliquid"] = hyper[symbol]

        if venues:
            current_snapshot[symbol] = venues

    history = load_history()
    history = append_history(history, current_snapshot, cfg)
    write_json_atomic(OI_HISTORY_PATH, OI_HISTORY_TMP_PATH, history)

    symbols_bucket = history.get("symbols", {})
    if not isinstance(symbols_bucket, dict):
        symbols_bucket = {}

    lookback_points = safe_int(cfg.get("comparison_lookback_points", 1), 1)
    min_valid_oi = safe_float(cfg.get("min_valid_oi", 0.0), 0.0)
    rising_threshold_pct = safe_float(cfg.get("rising_threshold_pct", 2.5), 2.5)
    falling_threshold_pct = safe_float(cfg.get("falling_threshold_pct", -2.5), -2.5)
    strong_rising_threshold_pct = safe_float(cfg.get("strong_rising_threshold_pct", 6.0), 6.0)
    strong_falling_threshold_pct = safe_float(cfg.get("strong_falling_threshold_pct", -6.0), -6.0)
    emit_neutral = bool(cfg.get("emit_neutral_change_rows", True))
    max_signals = safe_int(cfg.get("max_signals_per_run", 100), 100)

    change_rows: List[Dict[str, Any]] = []
    rising_count = 0
    falling_count = 0
    bullish_squeeze_count = 0
    bearish_squeeze_count = 0

    for symbol, series in symbols_bucket.items():
        if not isinstance(series, list) or not series:
            continue

        current_row = series[-1]
        if not isinstance(current_row, dict):
            continue

        previous_row = prior_point(series, lookback_points)
        if previous_row is None:
            continue

        current_oi = safe_float(current_row.get("avg_oi"), 0.0)
        previous_oi = safe_float(previous_row.get("avg_oi"), 0.0)

        if current_oi <= min_valid_oi or previous_oi <= min_valid_oi:
            continue

        delta_pct = pct_change(current_oi, previous_oi)
        entity = base_asset(symbol)
        venues = current_row.get("venues", {})

        change_rows.append(
            {
                "entity": entity,
                "current_oi": current_oi,
                "previous_oi": previous_oi,
                "delta_pct": delta_pct,
                "venues": venues,
            }
        )

        if emit_neutral:
            signals.append(
                build_change_signal(
                    entity=entity,
                    current_oi=current_oi,
                    previous_oi=previous_oi,
                    delta_pct=delta_pct,
                    venues=venues,
                )
            )

        if delta_pct >= rising_threshold_pct:
            strong = delta_pct >= strong_rising_threshold_pct
            rising_count += 1

            signals.append(
                build_rising_signal(
                    entity=entity,
                    current_oi=current_oi,
                    previous_oi=previous_oi,
                    delta_pct=delta_pct,
                    strong=strong,
                )
            )

            if strong:
                bullish_squeeze_count += 1
                signals.append(
                    build_bullish_squeeze_build_signal(
                        entity=entity,
                        current_oi=current_oi,
                        previous_oi=previous_oi,
                        delta_pct=delta_pct,
                    )
                )

        elif delta_pct <= falling_threshold_pct:
            strong = delta_pct <= strong_falling_threshold_pct
            falling_count += 1

            signals.append(
                build_falling_signal(
                    entity=entity,
                    current_oi=current_oi,
                    previous_oi=previous_oi,
                    delta_pct=delta_pct,
                    strong=strong,
                )
            )

            if strong:
                bearish_squeeze_count += 1
                signals.append(
                    build_bearish_squeeze_build_signal(
                        entity=entity,
                        current_oi=current_oi,
                        previous_oi=previous_oi,
                        delta_pct=delta_pct,
                    )
                )

        if len(signals) >= max_signals:
            break

    signals.append(
        build_summary_signal(
            rows=change_rows,
            rising_count=rising_count,
            falling_count=falling_count,
            bullish_squeeze_count=bullish_squeeze_count,
            bearish_squeeze_count=bearish_squeeze_count,
            summary_top_n=safe_int(cfg.get("summary_top_n", 8), 8),
        )
    )

    runtime = round(time.time() - started, 2)
    debug_log(
        cfg,
        f"symbols={len(current_snapshot)} change_rows={len(change_rows)} "
        f"rising={rising_count} falling={falling_count} "
        f"bullish_squeeze_build={bullish_squeeze_count} "
        f"bearish_squeeze_build={bearish_squeeze_count} "
        f"signals_returned={len(signals)} runtime={runtime}s"
    )

    return signals[:max_signals]


# ---------------------------------------------------
# DIRECT TEST MODE
# ---------------------------------------------------

if __name__ == "__main__":
    rows = fetch_open_interest_change_signals()
    print("count:", len(rows))
    for row in rows[:20]:
        print(
            getattr(row, "signal_type", None),
            getattr(row, "entity", None),
            getattr(row, "summary", None),
        )
