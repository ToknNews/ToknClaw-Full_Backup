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
# MODULE: analyst
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================

import json
import os
from datetime import datetime, timedelta, UTC

SNAPSHOT_DIR = "/opt/toknclaw/data/snapshots"
ROLLING_WINDOW_MINUTES = 60


def load_recent_snapshots():

    snapshots = []

    if not os.path.exists(SNAPSHOT_DIR):
        return snapshots

    cutoff = datetime.now(UTC) - timedelta(minutes=ROLLING_WINDOW_MINUTES)

    for file in sorted(os.listdir(SNAPSHOT_DIR)):

        if not file.endswith(".json"):
            continue

        path = os.path.join(SNAPSHOT_DIR, file)

        try:
            with open(path, "r", encoding="utf-8") as f:
                snap = json.load(f)

            ts_raw = snap.get("timestamp")
            if not ts_raw:
                continue

            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))

            if ts >= cutoff:
                snapshots.append(snap)

        except Exception:
            continue

    return snapshots


def compute_trend(values):

    if len(values) < 2:
        return "stable"

    if values[-1] > values[0]:
        return "rising"

    if values[-1] < values[0]:
        return "falling"

    return "stable"


def compute_delta(current_value, previous_value):

    absolute_change = current_value - previous_value

    if previous_value == 0:
        percent_change = None
    else:
        percent_change = round((absolute_change / previous_value) * 100, 2)

    return {
        "current": current_value,
        "previous": previous_value,
        "absolute_change": absolute_change,
        "percent_change": percent_change
    }


def analyze(snapshot):

    history = load_recent_snapshots()

    whale_values = []
    inflow_values = []
    outflow_values = []
    liquidation_values = []

    for snap in history:

        metrics = snap.get("metrics", {})

        whale_values.append(metrics.get("whale_activity_usd", 0))
        inflow_values.append(metrics.get("exchange_inflows_usd", 0))
        outflow_values.append(metrics.get("exchange_outflows_usd", 0))
        liquidation_values.append(metrics.get("defi_liquidations_usd", 0))

    current_metrics = snapshot.get("metrics", {})

    current_whales = current_metrics.get("whale_activity_usd", 0)
    current_inflows = current_metrics.get("exchange_inflows_usd", 0)
    current_outflows = current_metrics.get("exchange_outflows_usd", 0)
    current_liquidations = current_metrics.get("defi_liquidations_usd", 0)

    previous_whales = whale_values[-1] if whale_values else 0
    previous_inflows = inflow_values[-1] if inflow_values else 0
    previous_outflows = outflow_values[-1] if outflow_values else 0
    previous_liquidations = liquidation_values[-1] if liquidation_values else 0

    whale_trend = compute_trend(whale_values + [current_whales])
    inflow_trend = compute_trend(inflow_values + [current_inflows])
    outflow_trend = compute_trend(outflow_values + [current_outflows])
    liquidation_trend = compute_trend(liquidation_values + [current_liquidations])

    drivers = []

    if inflow_trend == "rising" and current_inflows > 0:
        drivers.append("exchange inflows rising")

    if liquidation_trend == "rising" and current_liquidations > 0:
        drivers.append("defi liquidations increasing")

    if whale_trend == "rising" and current_whales > 0:
        drivers.append("whale activity increasing")

    if outflow_trend == "rising" and current_outflows > 0:
        drivers.append("exchange outflows rising")

    trend = "neutral"

    if "exchange inflows rising" in drivers and "defi liquidations increasing" in drivers:
        trend = "bearish"

    elif "whale activity increasing" in drivers and "exchange outflows rising" in drivers:
        trend = "bullish"

    confidence = 0.8
    if len(drivers) >= 3:
        confidence = 0.88
    elif len(drivers) == 1:
        confidence = 0.72

    analysis = {
        "trend": trend,
        "drivers": drivers,
        "confidence": confidence
    }

    memory = {
        "exchange_flow_trend": inflow_trend,
        "exchange_flow_cycles": len(inflow_values) + (1 if current_inflows > 0 else 0),
        "exchange_outflow_trend": outflow_trend,
        "whale_activity_trend": whale_trend,
        "liquidation_trend": liquidation_trend
    }

    deltas = {
        "whale_activity_usd": compute_delta(current_whales, previous_whales),
        "exchange_inflows_usd": compute_delta(current_inflows, previous_inflows),
        "exchange_outflows_usd": compute_delta(current_outflows, previous_outflows),
        "defi_liquidations_usd": compute_delta(current_liquidations, previous_liquidations)
    }

    return analysis, memory, deltas
