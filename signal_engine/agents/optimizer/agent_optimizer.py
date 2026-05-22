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
# MODULE: agent_optimizer
# PURPOSE: Run optimizer v1 in recommend-only mode using paper-trading outcomes
#          and latest trading state to generate bounded recommendations.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This module is designed to:
• load optimizer configuration
• load paper trading and trading snapshot state
• compute bounded performance metrics
• generate recommend-only optimization outputs
• write JSON and Markdown reports
• remain additive and OpenClaw agent ready
"""

from __future__ import annotations

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Dict

from signal_engine.agents.optimizer.optimizer_metrics import compute_optimizer_metrics
from signal_engine.agents.optimizer.optimizer_recommendations import build_optimizer_recommendations
from signal_engine.agents.optimizer.optimizer_report import build_markdown_report

# ---------------------------------------------------
# PATHS / DEFAULTS
# ---------------------------------------------------

CONFIG_PATH = Path("/opt/toknclaw/config/agent_optimizer.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "mode": "recommend_only",
    "lookback": {
        "max_closed_positions": 200,
        "max_days": 14
    },
    "minimum_sample_sizes": {
        "per_reason": 8,
        "per_entity": 8,
        "per_direction": 10
    },
    "change_limits": {
        "max_weight_step": 0.05,
        "max_threshold_step": 0.03,
        "max_size_step_pct": 0.15
    },
    "promotion_policy": {
        "enabled": True,
        "minimum_paper_trades": 20,
        "minimum_win_rate": 0.52,
        "minimum_expectancy_usd": 0.0,
        "max_drawdown_pct": 8.0
    },
    "allowed_patch_targets": [],
    "agent_hooks": {
        "allow_apply_changes": False,
        "require_report_output": True
    },
    "paths": {
        "paper_trading_state": "/opt/toknclaw/data/paper_trading_state.json",
        "trading_snapshot": "/opt/toknclaw/data/snapshots/latest_snapshot_trading.json",
        "report_json": "/opt/toknclaw/data/optimizer/latest_optimizer_report.json",
        "report_md": "/opt/toknclaw/data/optimizer/latest_optimizer_report.md",
        "recommendations_json": "/opt/toknclaw/data/optimizer/latest_optimizer_recommendations.json",
        "history_dir": "/opt/toknclaw/data/optimizer/optimizer_history"
    }
}

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def clean_text(value: Any) -> str:
    return str(value or "").strip()


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    tmp_path.replace(path)


def write_text_atomic(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(payload)

    tmp_path.replace(path)


def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value

    return merged


def load_optimizer_config() -> Dict[str, Any]:
    raw = read_json(CONFIG_PATH, {})
    if not isinstance(raw, dict):
        raw = {}

    return merge_dicts(DEFAULT_CONFIG, raw)


def load_runtime_inputs(cfg: Dict[str, Any]) -> Dict[str, Any]:
    paths = safe_dict(cfg.get("paths"))

    paper_trading_state = read_json(Path(clean_text(paths.get("paper_trading_state"))), {})
    trading_snapshot = read_json(Path(clean_text(paths.get("trading_snapshot"))), {})
    paper_trading_cfg = read_json(Path("/opt/toknclaw/config/paper_trading_engine.json"), {})
    trading_universe_cfg = read_json(Path("/opt/toknclaw/config/trading_universe.json"), {})

    return {
        "paper_trading_state": safe_dict(paper_trading_state),
        "trading_snapshot": safe_dict(trading_snapshot),
        "paper_trading_cfg": safe_dict(paper_trading_cfg),
        "trading_universe_cfg": safe_dict(trading_universe_cfg),
    }

# ---------------------------------------------------
# MAIN
# ---------------------------------------------------

def run_optimizer() -> Dict[str, Any]:
    cfg = load_optimizer_config()

    if not bool(cfg.get("enabled", True)):
        return {
            "status": "disabled",
            "generated_at": datetime.now(UTC).isoformat(),
        }

    runtime_inputs = load_runtime_inputs(cfg)

    metrics = compute_optimizer_metrics(
        paper_state=runtime_inputs["paper_trading_state"],
        trading_snapshot=runtime_inputs["trading_snapshot"],
        optimizer_cfg=cfg,
    )

    recommendations = build_optimizer_recommendations(
        metrics=metrics,
        optimizer_cfg=cfg,
        paper_trading_cfg=runtime_inputs["paper_trading_cfg"],
        trading_universe_cfg=runtime_inputs["trading_universe_cfg"],
    )

    report = {
        "status": "ok",
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": clean_text(cfg.get("mode", "recommend_only")),
        "metrics": metrics,
        "recommendations": recommendations,
    }

    report_md = build_markdown_report(
        metrics=metrics,
        recommendations=recommendations,
    )

    paths = safe_dict(cfg.get("paths"))
    report_json_path = Path(clean_text(paths.get("report_json")))
    report_md_path = Path(clean_text(paths.get("report_md")))
    recommendations_json_path = Path(clean_text(paths.get("recommendations_json")))
    history_dir = Path(clean_text(paths.get("history_dir")))

    write_json_atomic(report_json_path, report)
    write_json_atomic(recommendations_json_path, recommendations)
    write_text_atomic(report_md_path, report_md)

    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = clean_text(report.get("generated_at")).replace(":", "-")

    write_json_atomic(history_dir / f"optimizer_report_{stamp}.json", report)
    write_text_atomic(history_dir / f"optimizer_report_{stamp}.md", report_md)

    print("[AGENT OPTIMIZER] complete")
    print(f"[AGENT OPTIMIZER] recommendations={recommendations.get('count', 0)}")
    print(f"[AGENT OPTIMIZER] report_json={report_json_path}")
    print(f"[AGENT OPTIMIZER] report_md={report_md_path}")

    return report


def main() -> None:
    run_optimizer()


if __name__ == "__main__":
    main()
