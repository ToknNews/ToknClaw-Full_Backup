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
# MODULE: backtest_runner
# PURPOSE: Replay historical trading snapshots through trade_signal_engine and
#          paper_trading_engine to produce durable backtest metrics, equity
#          curves, and OpenClaw-ready optimization artifacts.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This module is designed to:
• replay historical snapshot files in deterministic order
• rebuild trade signals from each snapshot
• run paper trading on each snapshot in sequence
• isolate backtest state from live trading state
• emit metrics, equity curve, attribution, and agent tuning notes
• remain additive and OpenClaw hook ready

Primary Inputs
--------------
/opt/toknclaw/data/backtest_snapshots/*.json
/opt/toknclaw/data/token_price_history.json
/opt/toknclaw/config/paper_trading_engine.json

Primary Outputs
---------------
/opt/toknclaw/data/backtests/latest_backtest_results.json
/opt/toknclaw/data/backtests/latest_backtest_state.json

OpenClaw Hooks
--------------
Agents should read:
• latest_backtest_results.json

Agents may tune:
• paper_trading_engine.json
• trade_signal_engine thresholds / weights
"""

from __future__ import annotations

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

import json
import math
import shutil
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple

from signal_engine.pipeline.trade_signal_engine import build_trade_signals
from signal_engine.pipeline.paper_trading_engine import build_paper_trading

# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

BACKTEST_SNAPSHOTS_DIR = Path("/opt/toknclaw/data/backtest_snapshots")
BACKTEST_OUTPUT_DIR = Path("/opt/toknclaw/data/backtests")

RESULTS_PATH = BACKTEST_OUTPUT_DIR / "latest_backtest_results.json"
STATE_PATH = BACKTEST_OUTPUT_DIR / "latest_backtest_state.json"
TMP_RESULTS_PATH = BACKTEST_OUTPUT_DIR / "latest_backtest_results.tmp"
TMP_STATE_PATH = BACKTEST_OUTPUT_DIR / "latest_backtest_state.tmp"

# 🔴 ISOLATED BACKTEST STATE
BACKTEST_STATE_PATH = Path("/opt/toknclaw/data/backtests/backtest_paper_state.json")
BACKTEST_STATE_TMP_PATH = Path("/opt/toknclaw/data/backtests/backtest_paper_state.tmp")
# 🔴 TEMP SNAPSHOT USED BY BACKTEST REPLAY
BACKTEST_TRADING_SNAPSHOT_PATH = Path("/opt/toknclaw/data/backtests/backtest_latest_snapshot.json")

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(UTC)


def now_iso() -> str:
    return utc_now().isoformat()


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def clean_upper(value: Any) -> str:
    return clean_text(value).upper()


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


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path: Path, tmp_path: Path, payload: Dict[str, Any]) -> None:
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp_path.replace(path)


def sorted_snapshot_paths(directory: Path) -> List[Path]:
    if not directory.exists():
        return []
    return sorted(
        [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".json"],
        key=lambda p: p.name,
    )


def peak_to_valley_drawdown(equity_curve: List[Dict[str, Any]]) -> float:
    if not equity_curve:
        return 0.0

    peak = None
    max_dd = 0.0

    for row in equity_curve:
        equity = safe_float(row.get("equity_usd"), 0.0)

        if peak is None or equity > peak:
            peak = equity

        if peak and peak > 0:
            dd = (peak - equity) / peak
            max_dd = max(max_dd, dd)

    return round(max_dd * 100.0, 4)


def sharpe_like_ratio(equity_curve: List[Dict[str, Any]]) -> float:
    if len(equity_curve) < 3:
        return 0.0

    returns: List[float] = []
    prev = None

    for row in equity_curve:
        equity = safe_float(row.get("equity_usd"), 0.0)
        if prev is not None and prev > 0:
            returns.append((equity - prev) / prev)
        prev = equity

    if len(returns) < 2:
        return 0.0

    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / max(len(returns) - 1, 1)
    std = math.sqrt(variance)

    if std == 0:
        return 0.0

    return round(mean_r / std, 6)


def infer_setup_family(position: Dict[str, Any]) -> str:
    signal_copy = safe_dict(position.get("signal_copy"))
    return clean_text(signal_copy.get("setup_family")) or clean_text(position.get("setup_family")) or "unknown"


def infer_direction(position: Dict[str, Any]) -> str:
    return clean_text(position.get("direction")) or "neutral"


def infer_side(position: Dict[str, Any]) -> str:
    return clean_text(position.get("side")) or "flat"

# ---------------------------------------------------
# SNAPSHOT PREP
# ---------------------------------------------------

def build_backtest_snapshot(raw_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = deepcopy(raw_snapshot)

    trade_signals = build_trade_signals(snapshot)
    snapshot["trade_signals"] = trade_signals

    return snapshot

# ---------------------------------------------------
# BACKTEST METRICS
# ---------------------------------------------------

def summarize_closed_positions(closed_positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_closed = len(closed_positions)
    realized_pnl = 0.0
    gross_profit = 0.0
    gross_loss = 0.0

    win_count = 0
    loss_count = 0
    flat_count = 0

    by_direction: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "flat": 0,
        "realized_pnl_usd": 0.0,
    })

    by_setup_family: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "flat": 0,
        "realized_pnl_usd": 0.0,
    })

    close_reason_counts: Counter = Counter()

    for position in closed_positions:
        pnl = safe_float(position.get("realized_pnl_usd"), 0.0)
        realized_pnl += pnl

        direction = infer_direction(position)
        setup_family = infer_setup_family(position)
        close_reason = clean_text(position.get("close_reason")) or "unknown"

        by_direction[direction]["count"] += 1
        by_direction[direction]["realized_pnl_usd"] += pnl

        by_setup_family[setup_family]["count"] += 1
        by_setup_family[setup_family]["realized_pnl_usd"] += pnl

        close_reason_counts[close_reason] += 1

        if pnl > 0:
            win_count += 1
            gross_profit += pnl
            by_direction[direction]["wins"] += 1
            by_setup_family[setup_family]["wins"] += 1
        elif pnl < 0:
            loss_count += 1
            gross_loss += abs(pnl)
            by_direction[direction]["losses"] += 1
            by_setup_family[setup_family]["losses"] += 1
        else:
            flat_count += 1
            by_direction[direction]["flat"] += 1
            by_setup_family[setup_family]["flat"] += 1

    win_rate = (win_count / total_closed) * 100.0 if total_closed > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

    return {
        "total_closed_positions": total_closed,
        "realized_pnl_usd": round(realized_pnl, 4),
        "gross_profit_usd": round(gross_profit, 4),
        "gross_loss_usd": round(gross_loss, 4),
        "win_count": win_count,
        "loss_count": loss_count,
        "flat_count": flat_count,
        "win_rate_pct": round(win_rate, 4),
        "profit_factor": round(profit_factor, 6),
        "by_direction": {
            key: {
                **value,
                "realized_pnl_usd": round(safe_float(value["realized_pnl_usd"]), 4),
            }
            for key, value in sorted(by_direction.items(), key=lambda x: x[0])
        },
        "by_setup_family": {
            key: {
                **value,
                "realized_pnl_usd": round(safe_float(value["realized_pnl_usd"]), 4),
            }
            for key, value in sorted(
                by_setup_family.items(),
                key=lambda x: (-safe_float(x[1].get("realized_pnl_usd"), 0.0), x[0]),
            )
        },
        "close_reason_counts": dict(close_reason_counts),
    }


def build_agent_feedback(results: Dict[str, Any]) -> Dict[str, Any]:
    setup_perf = safe_dict(results.get("closed_position_summary", {}).get("by_setup_family"))
    direction_perf = safe_dict(results.get("closed_position_summary", {}).get("by_direction"))

    weak_setups: List[Dict[str, Any]] = []
    strong_setups: List[Dict[str, Any]] = []

    for setup_family, payload in setup_perf.items():
        pnl = safe_float(payload.get("realized_pnl_usd"), 0.0)
        count = safe_int(payload.get("count"), 0)

        item = {
            "setup_family": setup_family,
            "count": count,
            "realized_pnl_usd": round(pnl, 4),
        }

        if pnl > 0:
            strong_setups.append(item)
        elif pnl < 0:
            weak_setups.append(item)

    strong_setups.sort(key=lambda x: (-x["realized_pnl_usd"], x["setup_family"]))
    weak_setups.sort(key=lambda x: (x["realized_pnl_usd"], x["setup_family"]))

    recommendations: List[str] = []

    total_closed = safe_int(results.get("closed_position_summary", {}).get("total_closed_positions"), 0)
    max_drawdown_pct = safe_float(results.get("max_drawdown_pct"), 0.0)
    profit_factor = safe_float(results.get("closed_position_summary", {}).get("profit_factor"), 0.0)

    if total_closed < 20:
        recommendations.append("Sample size is small. Extend replay window before retuning thresholds.")
    if max_drawdown_pct > 15.0:
        recommendations.append("Drawdown is elevated. Reduce sizing or tighten rotation/exit rules.")
    if profit_factor < 1.0 and total_closed > 0:
        recommendations.append("Profit factor is below 1.0. Downweight weak setup families before increasing size.")

    bearish_perf = safe_dict(direction_perf.get("bearish"))
    bullish_perf = safe_dict(direction_perf.get("bullish"))
    strong_bearish_perf = safe_dict(direction_perf.get("strong_bearish"))
    strong_bullish_perf = safe_dict(direction_perf.get("strong_bullish"))

    if safe_float(bearish_perf.get("realized_pnl_usd"), 0.0) + safe_float(strong_bearish_perf.get("realized_pnl_usd"), 0.0) > \
       safe_float(bullish_perf.get("realized_pnl_usd"), 0.0) + safe_float(strong_bullish_perf.get("realized_pnl_usd"), 0.0):
        recommendations.append("Short-side setups are outperforming long-side setups in this replay window.")
    else:
        recommendations.append("Long-side setups are outperforming short-side setups in this replay window.")

    return {
        "strong_setups": strong_setups[:10],
        "weak_setups": weak_setups[:10],
        "recommendations": recommendations[:8],
    }

# ---------------------------------------------------
# CORE RUNNER
# ---------------------------------------------------

def run_backtest(snapshot_dir: Path = BACKTEST_SNAPSHOTS_DIR) -> Dict[str, Any]:
    snapshot_dir = Path(snapshot_dir)
    snapshot_paths = sorted_snapshot_paths(snapshot_dir)

    if not snapshot_paths:
        payload = {
            "status": "error",
            "generated_at": now_iso(),
            "system": "ToknClaw",
            "module": "backtest_runner",
            "error": f"No snapshot files found in {snapshot_dir}",
            "input": {
                "snapshot_dir": str(snapshot_dir),
                "snapshot_file_count": 0,
            },
        }
        write_json_atomic(RESULTS_PATH, TMP_RESULTS_PATH, payload)
        return payload

    BACKTEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    equity_curve: List[Dict[str, Any]] = []
    replay_log: List[Dict[str, Any]] = []
    processed_snapshot_count = 0
    final_state: Dict[str, Any] = {}

    import signal_engine.pipeline.paper_trading_engine as pte

    original_state_path = pte.STATE_PATH
    original_tmp_path = pte.STATE_TMP_PATH
    original_snapshot_path = pte.SNAPSHOT_PATH

    try:
        # ---------------------------------------------------
        # ISOLATE BACKTEST STATE FROM LIVE SYSTEM
        # ---------------------------------------------------

        pte.STATE_PATH = BACKTEST_STATE_PATH
        pte.STATE_TMP_PATH = BACKTEST_STATE_TMP_PATH
        pte.SNAPSHOT_PATH = BACKTEST_TRADING_SNAPSHOT_PATH

        # clean prior backtest state so replay starts fresh
        if BACKTEST_STATE_PATH.exists():
            BACKTEST_STATE_PATH.unlink()

        if BACKTEST_STATE_TMP_PATH.exists():
            BACKTEST_STATE_TMP_PATH.unlink()

        # ---------------------------------------------------
        # REPLAY LOOP
        # ---------------------------------------------------

        for index, snapshot_path in enumerate(snapshot_paths, start=1):
            raw_snapshot = read_json_file(snapshot_path, {})
            if not isinstance(raw_snapshot, dict) or not raw_snapshot:
                replay_log.append(
                    {
                        "index": index,
                        "snapshot_file": snapshot_path.name,
                        "status": "skipped_invalid_snapshot",
                    }
                )
                continue

            prepared_snapshot = build_backtest_snapshot(raw_snapshot)

            BACKTEST_TRADING_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(BACKTEST_TRADING_SNAPSHOT_PATH, "w", encoding="utf-8") as f:
                json.dump(prepared_snapshot, f, indent=2)

            state = pte.build_paper_trading(prepared_snapshot)
            final_state = state if isinstance(state, dict) else {}
            processed_snapshot_count += 1

            portfolio = safe_dict(final_state.get("portfolio"))
            summary = safe_dict(final_state.get("summary"))

            equity_curve.append(
                {
                    "index": index,
                    "snapshot_file": snapshot_path.name,
                    "timestamp": raw_snapshot.get("timestamp"),
                    "equity_usd": round(safe_float(portfolio.get("equity_usd"), 0.0), 4),
                    "cash_usd": round(safe_float(portfolio.get("cash_usd"), 0.0), 4),
                    "open_position_count": safe_int(portfolio.get("open_position_count"), 0),
                    "closed_position_count": safe_int(portfolio.get("closed_position_count"), 0),
                }
            )

            replay_log.append(
                {
                    "index": index,
                    "snapshot_file": snapshot_path.name,
                    "status": "processed",
                    "trade_row_count": len(safe_list(prepared_snapshot.get("trade_signals", {}).get("rows"))),
                    "positions_opened_total": safe_int(summary.get("positions_opened"), 0),
                    "positions_closed_total": safe_int(summary.get("positions_closed"), 0),
                }
            )

        # ---------------------------------------------------
        # FINAL SUMMARIZATION
        # ---------------------------------------------------

        final_portfolio = safe_dict(final_state.get("portfolio"))
        closed_positions = safe_list(final_state.get("closed_positions"))

        closed_summary = summarize_closed_positions(closed_positions)
        max_dd = peak_to_valley_drawdown(equity_curve)
        sharpe_like = sharpe_like_ratio(equity_curve)

        results = {
            "status": "ok",
            "generated_at": now_iso(),
            "system": "ToknClaw",
            "module": "backtest_runner",
            "input": {
                "snapshot_dir": str(snapshot_dir),
                "snapshot_file_count": len(snapshot_paths),
                "processed_snapshot_count": processed_snapshot_count,
            },
            "portfolio": {
                "starting_cash_usd": round(safe_float(final_portfolio.get("starting_cash_usd"), 0.0), 4),
                "cash_usd": round(safe_float(final_portfolio.get("cash_usd"), 0.0), 4),
                "equity_usd": round(safe_float(final_portfolio.get("equity_usd"), 0.0), 4),
                "realized_pnl_usd": round(safe_float(final_portfolio.get("realized_pnl_usd"), 0.0), 4),
                "unrealized_pnl_usd": round(safe_float(final_portfolio.get("unrealized_pnl_usd"), 0.0), 4),
                "gross_exposure_usd": round(safe_float(final_portfolio.get("gross_exposure_usd"), 0.0), 4),
                "open_position_count": safe_int(final_portfolio.get("open_position_count"), 0),
                "closed_position_count": safe_int(final_portfolio.get("closed_position_count"), 0),
            },
            "max_drawdown_pct": max_dd,
            "sharpe_like_ratio": sharpe_like,
            "closed_position_summary": closed_summary,
            "equity_curve": equity_curve,
            "replay_log": replay_log[-250:],
        }

        results["agent_feedback"] = build_agent_feedback(results)

        write_json_atomic(RESULTS_PATH, TMP_RESULTS_PATH, results)
        write_json_atomic(
            STATE_PATH,
            TMP_STATE_PATH,
            final_state if isinstance(final_state, dict) else {},
        )

        return results

    except Exception as e:
        payload = {
            "status": "error",
            "generated_at": now_iso(),
            "system": "ToknClaw",
            "module": "backtest_runner",
            "error": str(e),
            "input": {
                "snapshot_dir": str(snapshot_dir),
                "snapshot_file_count": len(snapshot_paths),
                "processed_snapshot_count": processed_snapshot_count,
            },
            "equity_curve": equity_curve,
            "replay_log": replay_log[-250:],
        }
        write_json_atomic(RESULTS_PATH, TMP_RESULTS_PATH, payload)
        raise

    finally:
        # always restore live paper trading engine globals
        pte.STATE_PATH = original_state_path
        pte.STATE_TMP_PATH = original_tmp_path
        pte.SNAPSHOT_PATH = original_snapshot_path

# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

def main() -> None:
    results = run_backtest()

    summary = {
        "status": results.get("status"),
        "generated_at": results.get("generated_at"),
        "snapshot_file_count": safe_dict(results.get("input")).get("snapshot_file_count"),
        "processed_snapshot_count": safe_dict(results.get("input")).get("processed_snapshot_count"),
        "equity_usd": safe_dict(results.get("portfolio")).get("equity_usd"),
        "realized_pnl_usd": safe_dict(results.get("portfolio")).get("realized_pnl_usd"),
        "max_drawdown_pct": results.get("max_drawdown_pct"),
        "profit_factor": safe_dict(results.get("closed_position_summary")).get("profit_factor"),
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
