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
# MODULE: regime_transition_engine
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


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_recent_regimes(limit: int = LOOKBACK_FILES) -> List[str]:
    if not SNAPSHOT_DIR.exists():
        return []

    files = sorted(
        [p for p in SNAPSHOT_DIR.glob("snapshot_*.json") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]

    regimes = []

    for path in reversed(files):
        try:
            data = json.loads(path.read_text())
            regime = _safe_dict(data.get("market_regime")).get("name")
            if regime:
                regimes.append(str(regime))
        except Exception:
            continue

    return regimes


def build_regime_transition(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    current = str(_safe_dict(snapshot.get("market_regime")).get("name") or "unknown")
    history = _load_recent_regimes()

    previous = history[-2] if len(history) >= 2 else None
    changed = bool(previous and previous != current)

    same_count = sum(1 for x in history if x == current)
    stability_score = round(same_count / max(len(history), 1), 2)

    transition_type = "stable"
    if changed:
        transition_type = "regime_shift"
    elif stability_score < 0.4:
        transition_type = "fragile"
    elif stability_score >= 0.75:
        transition_type = "persistent"

    alerts = []
    if changed:
        alerts.append({
            "type": "regime_shift",
            "severity": "high",
            "previous_regime": previous,
            "current_regime": current,
        })
    elif stability_score < 0.4:
        alerts.append({
            "type": "regime_fragility",
            "severity": "medium",
            "current_regime": current,
        })

    return {
        "current_regime": current,
        "previous_regime": previous,
        "changed": changed,
        "transition_type": transition_type,
        "stability_score": stability_score,
        "history_depth": len(history),
        "alerts": alerts,
    }
