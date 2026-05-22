#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — OPENCLAW TELEGRAM AGENT
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
# MODULE: reef_agent
# PURPOSE:
# - Reload strategy decisions on a slower operator-safe cadence
# - Send Telegram approval requests with inline buttons
# - Expire unanswered proposals after a TTL
# - Apply safe config-only patches after approval
# - Act as an operator surface for trade opens, trade closes, and system snapshots
# ============================================================
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

TELEGRAM_TOKEN = os.getenv("REEF_TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("REEF_TELEGRAM_CHAT_ID", "").strip()

DECISIONS_PATH = Path("/opt/toknclaw/data/analytics/strategy_decisions.json")
WEIGHTS_PATH = Path("/opt/toknclaw/config/trade_signal_weights.json")
BACKUP_DIR = Path("/opt/toknclaw/config/backups")
STATE_PATH = Path("/opt/toknclaw/data/analytics/reef_agent_state.json")

TRADES_PATH = Path("/opt/toknclaw/data/paper_trading_state.json")
SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot_trading.json")
CLUSTERS_PATH = Path("/opt/toknclaw/data/analytics/cluster_active.json")

POLL_INTERVAL_SEC = 5
DECISION_REFRESH_SEC = 7200            # 2 hours
PROPOSAL_TTL_SEC = 1800               # 30 minutes
COOLDOWN_AFTER_REJECT_SEC = 1800      # 30 minutes
COOLDOWN_AFTER_EXPIRE_SEC = 900       # 15 minutes
MIN_WEIGHT = 0.10

SNAPSHOT_ALERT_SEC = 1800             # 30 minutes
SYSTEM_WARNING_SEC = 1800             # 30 minutes
TRADE_CLOSE_ALERT_LIMIT = 5
TRADE_OPEN_ALERT_LIMIT = 5

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(UTC)

def utc_now_iso() -> str:
    return utc_now().isoformat()

def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}

def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []

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

def clean_text(value: Any) -> str:
    return str(value or "").strip()

def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp_path.replace(path)

def backup_file(path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_name = f"{path.name}.{utc_now().strftime('%Y%m%d_%H%M%S')}.bak"
    backup_path = BACKUP_DIR / backup_name
    write_json(backup_path, read_json(path, {}))
    return backup_path

def log(message: str) -> None:
    print(f"[REEF] {message}", flush=True)

# ---------------------------------------------------
# TELEGRAM
# ---------------------------------------------------

def require_telegram_config() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("REEF_TELEGRAM_TOKEN is not set")
    if not CHAT_ID:
        raise RuntimeError("REEF_TELEGRAM_CHAT_ID is not set")

def telegram_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"

def send_message(text: str) -> None:
    try:
        requests.post(
            telegram_url("sendMessage"),
            json={"chat_id": CHAT_ID, "text": text},
            timeout=20,
        )
    except Exception as exc:
        log(f"send_message failed: {exc}")

def send_proposal(proposal_key: str, text: str) -> None:
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"APPROVE|{proposal_key}"},
                {"text": "❌ Reject", "callback_data": f"REJECT|{proposal_key}"},
            ]]
        },
    }
    try:
        requests.post(telegram_url("sendMessage"), json=payload, timeout=20)
    except Exception as exc:
        log(f"send_proposal failed: {exc}")

def get_updates(offset: Optional[int] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"timeout": 20}
    if offset is not None:
        params["offset"] = offset
    try:
        r = requests.get(telegram_url("getUpdates"), params=params, timeout=30)
        return r.json()
    except Exception as exc:
        log(f"get_updates failed: {exc}")
        return {"ok": False, "result": []}

def answer_callback(callback_id: str) -> None:
    try:
        requests.post(
            telegram_url("answerCallbackQuery"),
            json={"callback_query_id": callback_id},
            timeout=20,
        )
    except Exception as exc:
        log(f"answer_callback failed: {exc}")

# ---------------------------------------------------
# STATE
# ---------------------------------------------------

def _default_operator_state() -> Dict[str, Any]:
    return {
        "bootstrapped": False,
        "known_open_ids": [],
        "known_closed_ids": [],
        "last_snapshot_alert_ts": 0.0,
        "last_warning_ts": 0.0,
        "last_equity_usd": None,
    }

def load_state() -> Dict[str, Any]:
    state = read_json(STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("last_update_id", None)
    state.setdefault("pending", {})
    state.setdefault("history", {})
    state.setdefault("last_decision_reload_at", None)
    state.setdefault("operator", _default_operator_state())
    if not isinstance(state.get("operator"), dict):
        state["operator"] = _default_operator_state()
    for k, v in _default_operator_state().items():
        state["operator"].setdefault(k, v)
    return state

def save_state(state: Dict[str, Any]) -> None:
    write_json(STATE_PATH, state)

# ---------------------------------------------------
# PROPOSAL MODEL
# ---------------------------------------------------

def proposal_fingerprint(strategy_key: str, action: Dict[str, Any], sample_confidence: float) -> str:
    base = {
        "strategy_key": clean_text(strategy_key),
        "action_type": clean_text(action.get("type")),
        "target": clean_text(action.get("target")),
        "operation": clean_text(safe_dict(action.get("patch")).get("operation")),
        "sample_confidence": round(sample_confidence, 4),
        "time_bucket": int(time.time() // 7200),  # 2 hour window
    }
    raw = json.dumps(base, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def build_proposal_text(strategy_key: str, realized: Dict[str, Any], action: Dict[str, Any], sample_confidence: float) -> str:
    health = clean_text(realized.get("health")) or "unknown"
    count = safe_int(realized.get("count"), 0)
    pnl = safe_float(realized.get("realized_pnl_usd"), 0.0)
    op = clean_text(safe_dict(action.get("patch")).get("operation")) or "review"
    target = clean_text(action.get("target")) or strategy_key

    return (
        "🌊 Reef Optimization Proposal\n\n"
        f"Strategy: {strategy_key}\n"
        f"Health: {health}\n"
        f"Closed Sample: {count}\n"
        f"Realized PnL: {pnl:.4f}\n"
        f"Sample Confidence: {sample_confidence:.2f}\n\n"
        f"Proposed Action:\n"
        f"→ {op} on {target}\n\n"
        "This request expires automatically if left unanswered."
    )

def build_candidate_proposals(decisions_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    proposals: List[Dict[str, Any]] = []
    current_weights = read_json(WEIGHTS_PATH, {})

    for row in safe_list(decisions_payload.get("strategy_decisions")):
        row = safe_dict(row)

        strategy_key = clean_text(row.get("strategy_key"))
        realized = safe_dict(row.get("realized"))
        actions = safe_list(row.get("actions"))
        sample_confidence = safe_float(row.get("sample_confidence"), 0.0)

        if not strategy_key or not actions:
            continue

        for action in actions:
            action = safe_dict(action)
            patch = safe_dict(action.get("patch"))
            config_file = clean_text(patch.get("config_file"))

            if config_file and config_file != "trade_signal_weights.json":
                continue

            operation = clean_text(patch.get("operation"))
            if operation != "downweight":
                continue

            current_weight = safe_float(current_weights.get(strategy_key), 1.0)
            if current_weight <= MIN_WEIGHT:
                log(f"Skipping proposal for {strategy_key}: already at MIN_WEIGHT ({current_weight})")
                continue

            proposal_key = proposal_fingerprint(strategy_key, action, sample_confidence)

            proposals.append({
                "proposal_key": proposal_key,
                "strategy_key": strategy_key,
                "realized": realized,
                "action": action,
                "sample_confidence": sample_confidence,
                "text": build_proposal_text(strategy_key, realized, action, sample_confidence),
            })

    return proposals

# ---------------------------------------------------
# PATCH APPLICATION
# ---------------------------------------------------

def apply_weight_patch(strategy_key: str) -> Tuple[bool, str]:
    config = read_json(WEIGHTS_PATH, {})
    if not isinstance(config, dict):
        return False, "trade_signal_weights.json is missing or invalid"

    if strategy_key not in config:
        return False, f"{strategy_key} not found in trade_signal_weights.json"

    old = safe_float(config[strategy_key], 1.0)
    new = max(round(old * 0.5, 4), MIN_WEIGHT)

    if new == old:
        log(f"NO-OP patch skipped {strategy_key}: already at minimum ({old})")
        return False, f"{strategy_key} already at minimum ({old})"

    backup_path = backup_file(WEIGHTS_PATH)
    config[strategy_key] = new
    write_json(WEIGHTS_PATH, config)

    log(f"Applying patch {strategy_key}: {old} → {new}")
    return True, f"{strategy_key}: {old} → {new} (backup: {backup_path})"

# ---------------------------------------------------
# OPERATOR SURFACE
# ---------------------------------------------------

def _trade_id(row: Dict[str, Any]) -> str:
    trade_id = clean_text(row.get("trade_id"))
    if trade_id:
        return trade_id
    entity = clean_text(row.get("entity"))
    opened_at = clean_text(row.get("opened_at"))
    status = clean_text(row.get("status"))
    return f"{entity}|{opened_at}|{status}"

def _format_trade_open(row: Dict[str, Any]) -> str:
    entity = clean_text(row.get("entity")) or "UNKNOWN"
    direction = clean_text(row.get("direction")) or "unknown"
    entry = safe_float(row.get("entry_price_usd"), 0.0)
    size = safe_float(row.get("position_size_usd"), 0.0)
    confidence = safe_float(row.get("confidence"), 0.0)
    opened_at = clean_text(row.get("opened_at")) or "unknown"
    source_title = clean_text(row.get("source_title")) or "trade signal"

    return (
        "🚀 Trade Opened\n\n"
        f"Entity: {entity}\n"
        f"Direction: {direction}\n"
        f"Entry: ${entry:.8f}\n"
        f"Size: ${size:.2f}\n"
        f"Confidence: {confidence:.3f}\n"
        f"Opened: {opened_at}\n"
        f"Source: {source_title}"
    )

def _format_trade_close(row: Dict[str, Any]) -> str:
    entity = clean_text(row.get("entity")) or "UNKNOWN"
    direction = clean_text(row.get("direction")) or "unknown"
    entry = safe_float(row.get("entry_price_usd"), 0.0)
    exit_price = safe_float(row.get("exit_price_usd"), 0.0)
    pnl = safe_float(row.get("realized_pnl_usd"), 0.0)
    pnl_pct = safe_float(row.get("realized_pnl_pct"), 0.0)
    close_reason = clean_text(row.get("close_reason")) or "unknown"
    closed_at = clean_text(row.get("closed_at")) or "unknown"

    emoji = "📈" if pnl >= 0 else "📉"

    return (
        f"{emoji} Trade Closed\n\n"
        f"Entity: {entity}\n"
        f"Direction: {direction}\n"
        f"Entry: ${entry:.8f}\n"
        f"Exit: ${exit_price:.8f}\n"
        f"PnL: ${pnl:.4f} ({pnl_pct:.4f}%)\n"
        f"Reason: {close_reason}\n"
        f"Closed: {closed_at}"
    )

def _load_trade_state() -> Dict[str, Any]:
    data = read_json(TRADES_PATH, {})
    return data if isinstance(data, dict) else {}

def _load_snapshot_state() -> Dict[str, Any]:
    data = read_json(SNAPSHOT_PATH, {})
    return data if isinstance(data, dict) else {}

def _load_cluster_state() -> Dict[str, Any]:
    data = read_json(CLUSTERS_PATH, {})
    return data if isinstance(data, dict) else {}

def _get_system_snapshot() -> Dict[str, Any]:
    trades = _load_trade_state()
    snapshot = _load_snapshot_state()
    clusters = _load_cluster_state()

    portfolio = safe_dict(trades.get("portfolio"))
    trade_signals = safe_dict(snapshot.get("trade_signals"))
    trade_summary = safe_dict(trade_signals.get("summary"))
    cluster_rows = safe_list(clusters.get("clusters"))

    top_clusters: List[str] = []
    for row in cluster_rows[:3]:
        row = safe_dict(row)
        title = clean_text(row.get("title"))
        if title:
            top_clusters.append(title)

    return {
        "equity_usd": safe_float(portfolio.get("equity_usd"), 0.0),
        "realized_pnl_usd": safe_float(portfolio.get("realized_pnl_usd"), 0.0),
        "open_position_count": safe_int(portfolio.get("open_position_count"), 0),
        "closed_position_count": safe_int(portfolio.get("closed_position_count"), 0),
        "strong_bullish_count": safe_int(trade_summary.get("strong_bullish_count"), 0),
        "bullish_count": safe_int(trade_summary.get("bullish_count"), 0),
        "neutral_count": safe_int(trade_summary.get("neutral_count"), 0),
        "no_trade_count": safe_int(trade_summary.get("no_trade_count"), 0),
        "bearish_count": safe_int(trade_summary.get("bearish_count"), 0),
        "strong_bearish_count": safe_int(trade_summary.get("strong_bearish_count"), 0),
        "top_clusters": top_clusters,
    }

def _format_system_snapshot(snapshot: Dict[str, Any]) -> str:
    clusters = snapshot.get("top_clusters") or []
    cluster_text = ", ".join(clusters) if clusters else "none"

    return (
        "📊 Reef System Snapshot\n\n"
        f"Equity: ${safe_float(snapshot.get('equity_usd'), 0.0):.2f}\n"
        f"Realized PnL: ${safe_float(snapshot.get('realized_pnl_usd'), 0.0):.2f}\n"
        f"Open Positions: {safe_int(snapshot.get('open_position_count'), 0)}\n"
        f"Closed Positions: {safe_int(snapshot.get('closed_position_count'), 0)}\n\n"
        f"Signals:\n"
        f"• Strong Bullish: {safe_int(snapshot.get('strong_bullish_count'), 0)}\n"
        f"• Bullish: {safe_int(snapshot.get('bullish_count'), 0)}\n"
        f"• Neutral: {safe_int(snapshot.get('neutral_count'), 0)}\n"
        f"• No Trade: {safe_int(snapshot.get('no_trade_count'), 0)}\n"
        f"• Bearish: {safe_int(snapshot.get('bearish_count'), 0)}\n"
        f"• Strong Bearish: {safe_int(snapshot.get('strong_bearish_count'), 0)}\n\n"
        f"Top Clusters: {cluster_text}"
    )

def bootstrap_operator_state(state: Dict[str, Any]) -> Dict[str, Any]:
    operator = safe_dict(state.get("operator"))
    if operator.get("bootstrapped"):
        return state

    trades = _load_trade_state()
    open_positions = safe_dict(trades.get("open_positions"))
    closed_positions = safe_list(trades.get("closed_positions"))

    operator["known_open_ids"] = sorted([_trade_id(safe_dict(v)) for v in open_positions.values()])
    operator["known_closed_ids"] = sorted([_trade_id(safe_dict(v)) for v in closed_positions])
    operator["last_snapshot_alert_ts"] = 0.0
    operator["last_warning_ts"] = 0.0
    operator["last_equity_usd"] = safe_float(safe_dict(trades.get("portfolio")).get("equity_usd"), 0.0)
    operator["bootstrapped"] = True

    state["operator"] = operator
    log("operator state bootstrapped")
    return state

def emit_trade_alerts(state: Dict[str, Any]) -> Dict[str, Any]:
    operator = safe_dict(state.get("operator"))
    trades = _load_trade_state()

    open_positions = safe_dict(trades.get("open_positions"))
    closed_positions = safe_list(trades.get("closed_positions"))

    current_open: Dict[str, Dict[str, Any]] = {}
    for row in open_positions.values():
        row = safe_dict(row)
        current_open[_trade_id(row)] = row

    current_closed: Dict[str, Dict[str, Any]] = {}
    for row in closed_positions:
        row = safe_dict(row)
        current_closed[_trade_id(row)] = row

    known_open_ids = set(safe_list(operator.get("known_open_ids")))
    known_closed_ids = set(safe_list(operator.get("known_closed_ids")))

    new_open_ids = [k for k in current_open.keys() if k not in known_open_ids]
    new_closed_ids = [k for k in current_closed.keys() if k not in known_closed_ids]

    if new_open_ids:
        for trade_id in new_open_ids[:TRADE_OPEN_ALERT_LIMIT]:
            send_message(_format_trade_open(current_open[trade_id]))
            log(f"trade open alert sent: {trade_id}")

    if new_closed_ids:
        # newest closed first
        new_closed_rows = [current_closed[k] for k in new_closed_ids]
        new_closed_rows.sort(key=lambda x: clean_text(safe_dict(x).get("closed_at")), reverse=True)
        for row in new_closed_rows[:TRADE_CLOSE_ALERT_LIMIT]:
            send_message(_format_trade_close(safe_dict(row)))
            log(f"trade close alert sent: {_trade_id(safe_dict(row))}")

    operator["known_open_ids"] = sorted(current_open.keys())
    operator["known_closed_ids"] = sorted(current_closed.keys())
    state["operator"] = operator
    return state

def maybe_send_system_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    operator = safe_dict(state.get("operator"))
    now_ts = time.time()
    last_snapshot_alert_ts = safe_float(operator.get("last_snapshot_alert_ts"), 0.0)

    if (now_ts - last_snapshot_alert_ts) < SNAPSHOT_ALERT_SEC:
        return state

    snapshot = _get_system_snapshot()
    send_message(_format_system_snapshot(snapshot))
    operator["last_snapshot_alert_ts"] = now_ts
    operator["last_equity_usd"] = safe_float(snapshot.get("equity_usd"), 0.0)
    state["operator"] = operator
    log("system snapshot alert sent")
    return state

def maybe_send_system_warning(state: Dict[str, Any]) -> Dict[str, Any]:
    operator = safe_dict(state.get("operator"))
    now_ts = time.time()
    last_warning_ts = safe_float(operator.get("last_warning_ts"), 0.0)

    if (now_ts - last_warning_ts) < SYSTEM_WARNING_SEC:
        return state

    snapshot = _get_system_snapshot()
    no_trade_count = safe_int(snapshot.get("no_trade_count"), 0)
    strong_bullish = safe_int(snapshot.get("strong_bullish_count"), 0)
    strong_bearish = safe_int(snapshot.get("strong_bearish_count"), 0)
    bullish = safe_int(snapshot.get("bullish_count"), 0)
    bearish = safe_int(snapshot.get("bearish_count"), 0)
    open_positions = safe_int(snapshot.get("open_position_count"), 0)

    actionable = strong_bullish + strong_bearish + bullish + bearish

    if actionable == 0 and no_trade_count > 0 and open_positions == 0:
        send_message(
            "🚨 Reef Warning\n\n"
            "System is producing only stand-aside signals.\n"
            "No actionable directional trades detected in the current snapshot."
        )
        operator["last_warning_ts"] = now_ts
        state["operator"] = operator
        log("system warning alert sent")

    return state

# ---------------------------------------------------
# PROPOSAL LIFECYCLE
# ---------------------------------------------------

def should_send_again(history_entry: Dict[str, Any]) -> bool:
    status = clean_text(history_entry.get("status"))
    last_ts = safe_float(history_entry.get("ts"), 0.0)
    now_ts = time.time()

    if status == "approved":
        return False
    if status == "rejected":
        return (now_ts - last_ts) >= COOLDOWN_AFTER_REJECT_SEC
    if status == "expired":
        return (now_ts - last_ts) >= COOLDOWN_AFTER_EXPIRE_SEC
    if status == "sent":
        return False
    return True

def expire_stale_pending(state: Dict[str, Any]) -> None:
    pending = safe_dict(state.get("pending"))
    history = safe_dict(state.get("history"))
    now_ts = time.time()

    expired_keys: List[str] = []

    for proposal_key, meta in pending.items():
        meta = safe_dict(meta)
        sent_ts = safe_float(meta.get("sent_ts"), 0.0)
        strategy_key = clean_text(meta.get("strategy_key")) or "unknown"

        if sent_ts and (now_ts - sent_ts) >= PROPOSAL_TTL_SEC:
            expired_keys.append(proposal_key)
            history[proposal_key] = {
                "status": "expired",
                "ts": now_ts,
                "strategy_key": strategy_key,
            }
            send_message(f"⌛ Reef proposal expired: {strategy_key}")

    for proposal_key in expired_keys:
        pending.pop(proposal_key, None)

    state["pending"] = pending
    state["history"] = history

def reload_and_send_proposals(state: Dict[str, Any]) -> Dict[str, Any]:
    decisions_payload = read_json(DECISIONS_PATH, {})
    pending = safe_dict(state.get("pending"))
    history = safe_dict(state.get("history"))

    candidates = build_candidate_proposals(decisions_payload)
    sent_count = 0

    for candidate in candidates:
        proposal_key = candidate["proposal_key"]
        strategy_key = candidate["strategy_key"]

        if proposal_key in pending:
            continue

        if proposal_key in history and not should_send_again(safe_dict(history.get(proposal_key))):
            continue

        send_proposal(proposal_key, candidate["text"])

        pending[proposal_key] = {
            "proposal_key": proposal_key,
            "strategy_key": strategy_key,
            "sent_ts": time.time(),
            "action": candidate["action"],
            "sample_confidence": candidate["sample_confidence"],
        }
        history[proposal_key] = {
            "status": "sent",
            "ts": time.time(),
            "strategy_key": strategy_key,
        }
        sent_count += 1
        log(f"sent proposal: {strategy_key} ({proposal_key})")

    state["pending"] = pending
    state["history"] = history
    state["last_decision_reload_at"] = utc_now_iso()

    if sent_count == 0:
        log("decision reload complete: no new proposals")

    return state

def process_callback(state: Dict[str, Any], callback: Dict[str, Any]) -> Dict[str, Any]:
    pending = safe_dict(state.get("pending"))
    history = safe_dict(state.get("history"))

    data = clean_text(callback.get("data"))
    callback_id = clean_text(callback.get("id"))

    if callback_id:
        answer_callback(callback_id)

    if "|" not in data:
        return state

    cmd, proposal_key = data.split("|", 1)
    meta = safe_dict(pending.get(proposal_key))

    if not meta:
        send_message("⚠️ Reef request no longer active.")
        return state

    strategy_key = clean_text(meta.get("strategy_key"))
    now_ts = time.time()

    if cmd == "APPROVE":
        ok, result = apply_weight_patch(strategy_key)
        if ok:
            send_message(f"✅ Applied: {result}")
            history[proposal_key] = {
                "status": "approved",
                "ts": now_ts,
                "strategy_key": strategy_key,
            }
        else:
            send_message(f"⚠️ Approval failed: {result}")
            history[proposal_key] = {
                "status": "error",
                "ts": now_ts,
                "strategy_key": strategy_key,
            }
        pending.pop(proposal_key, None)

    elif cmd == "REJECT":
        send_message(f"❌ Rejected: {strategy_key}")
        history[proposal_key] = {
            "status": "rejected",
            "ts": now_ts,
            "strategy_key": strategy_key,
        }
        pending.pop(proposal_key, None)

    state["pending"] = pending
    state["history"] = history
    return state

# ---------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------

def run_agent() -> None:
    require_telegram_config()

    state = load_state()
    state = bootstrap_operator_state(state)
    save_state(state)

    last_update_id = state.get("last_update_id")

    send_message("🌊 Reef Agent online | ToknClaw Optimization + Operator")
    log("agent started")

    last_reload_ts = 0.0

    while True:
        now_ts = time.time()

        expire_stale_pending(state)

        # operator surface
        state = emit_trade_alerts(state)
        state = maybe_send_system_warning(state)
        state = maybe_send_system_snapshot(state)

        # slower decision reload cadence
        if (now_ts - last_reload_ts) >= DECISION_REFRESH_SEC:
            state = reload_and_send_proposals(state)
            save_state(state)
            last_reload_ts = now_ts

        updates = get_updates(last_update_id)
        for update in safe_list(updates.get("result")):
            update = safe_dict(update)
            update_id = update.get("update_id")
            if update_id is not None:
                last_update_id = safe_int(update_id) + 1
                state["last_update_id"] = last_update_id

            callback = safe_dict(update.get("callback_query"))
            if callback:
                state = process_callback(state, callback)
                save_state(state)

        save_state(state)
        time.sleep(POLL_INTERVAL_SEC)

# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    run_agent()
