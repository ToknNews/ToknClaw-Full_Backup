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
# MODULE: tokenterminal_metrics
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


import json
import re
from pathlib import Path
from datetime import datetime
from models.signal import Signal

TOKENTERMINAL_PATH = Path("/opt/toknclaw/data/openclaw/tokenterminal_metrics.json")

USD_RE = re.compile(r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*([MBK]?)", re.IGNORECASE)


# ---------------------------------------------------
# VALUE PARSER
# ---------------------------------------------------

def _parse_usd_value(value):

    if value is None:
        return None

    text = str(value)

    match = USD_RE.search(text)

    if not match:
        return None

    number = float(match.group(1))
    suffix = (match.group(2) or "").upper()

    if suffix == "B":
        number *= 1_000_000_000
    elif suffix == "M":
        number *= 1_000_000
    elif suffix == "K":
        number *= 1_000

    return number


# ---------------------------------------------------
# ENTITY NORMALIZATION
# ---------------------------------------------------

def _normalize_entity(entity):

    if not entity:
        return None

    return str(entity).upper().strip()


# ---------------------------------------------------
# SIGNAL TYPE INFERENCE
# ---------------------------------------------------

def _infer_signal_type(metric, summary):

    blob = f"{metric} {summary}".lower()

    if "revenue" in blob:
        return "protocol_revenue"

    if "fee" in blob:
        return "protocol_fees"

    if "user" in blob:
        return "protocol_users"

    if "growth" in blob:
        return "protocol_growth"

    return "protocol_metric"


# ---------------------------------------------------
# CONFIDENCE SCORE
# ---------------------------------------------------

def _infer_confidence(signal_type, value_usd):

    base = 0.84

    if signal_type == "protocol_revenue":
        base = 0.88

    elif signal_type == "protocol_fees":
        base = 0.86

    elif signal_type == "protocol_users":
        base = 0.85

    if value_usd:
        base += 0.02

    return min(base, 0.92)


# ---------------------------------------------------
# BUILD TOKEN TERMINAL URL
# ---------------------------------------------------

def _build_protocol_url(protocol):

    if not protocol:
        return "https://tokenterminal.com"

    slug = str(protocol).lower().replace(" ", "-")

    return f"https://tokenterminal.com/terminal/projects/{slug}"


# ---------------------------------------------------
# MAIN COLLECTOR
# ---------------------------------------------------

def fetch_tokenterminal_signals():

    if not TOKENTERMINAL_PATH.exists():
        return []

    try:
        data = json.loads(TOKENTERMINAL_PATH.read_text())
    except Exception:
        print("[TOKENTERMINAL] invalid JSON handoff")
        return []

    if not isinstance(data, list):
        return []

    signals = []

    for item in data[:25]:

        if not isinstance(item, dict):
            continue

        entity = _normalize_entity(item.get("token"))
        protocol = item.get("protocol") or entity
        metric = item.get("metric") or "protocol metric"

        raw_value = item.get("value")
        summary = item.get("summary") or ""
        extra_context = item.get("context") or {}

        signal_type = _infer_signal_type(metric, summary)

        value_usd = _parse_usd_value(raw_value)

        title = f"{protocol} {metric}"

        if raw_value:
            title = f"{protocol} {metric}: {raw_value}"

        raw_url = _build_protocol_url(protocol)

        signal = Signal(
            timestamp=datetime.utcnow(),
            source="tokenterminal",
            signal_type=signal_type,
            entity=entity,
            title=title,
            summary=summary or title,
            confidence=_infer_confidence(signal_type, value_usd),
            sentiment_score=None,
            raw_url=raw_url
        )

        # Attach structured fields for clusters / UI

        try:
            signal.value_usd = value_usd
        except Exception:
            pass

        try:
            signal.metric = metric
        except Exception:
            pass

        try:
            signal.protocol = protocol
        except Exception:
            pass

        try:
            signal.context = extra_context
        except Exception:
            pass

        signals.append(signal)

    return signals
