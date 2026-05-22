#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — BACKEND API ENTRYPOINT
# ============================================================
#
# ████████╗ ██████╗ ██╗  ██╗███╗   ██╗ ██████╗██╗      █████╗ ██╗    ██╗
# ╚══██╔══╝██╔═══██╗██║ ██╔╝████╗  ██║██╔════╝██║     ██╔══██╗██║    ██║
#    ██║   ██║   ██║█████╔╝ ██╔██╗ ██║██║     ██║     ███████║██║ █╗ ██║
#    ██║   ██║   ██║██╔═██╗ ██║╚██╗██║██║     ██║     ██╔══██║██║███╗██║
#    ██║   ╚██████╔╝██║  ██╗██║ ╚████║╚██████╗███████╗██║  ██║╚███╔███╔╝
#    ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
#
# SYSTEM: ToknClaw Backend
# MODULE: app
# PURPOSE:
# - Expose read-only ToknClaw trading state to ToknNews frontend
# - Serve portfolio, positions, sizing, leverage, and decision data
# - Provide browser-safe CORS headers for toknnews.com
# ============================================================
"""

from flask import Flask, jsonify
from pathlib import Path
from backend.services.snapshot_archive import append_snapshot
import json

app = Flask(__name__)

BASE = Path("/opt/toknclaw")
PATHS = {
    "paper": BASE / "data/paper_trading_state.json",
    "snapshot": BASE / "data/snapshots/latest_snapshot_trading.json",
    "decisions": BASE / "data/analytics/strategy_decisions.json",
    "sizing": BASE / "data/analytics/trade_sizing.json",
    "leverage": BASE / "data/analytics/trade_leverage.json",
    "performance": BASE / "data/analytics/strategy_performance.json",
    "clusters": BASE / "data/analytics/cluster_active.json",
    "health": BASE / "data/analytics/cluster_collector_health.json",
}

def load_json(path: Path):
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "https://toknnews.com"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.route("/health")
def health():
    return jsonify({"status": "ok", "system": "ToknClaw API"})

@app.route("/portfolio")
def portfolio():
    return jsonify(load_json(PATHS["paper"]).get("portfolio", {}))

@app.route("/open_positions")
def open_positions():
    return jsonify(list(load_json(PATHS["paper"]).get("open_positions", {}).values()))

@app.route("/performance")
def performance():
    return jsonify(load_json(PATHS["performance"]))

@app.route("/decisions")
def decisions():
    return jsonify(load_json(PATHS["decisions"]))

@app.route("/sizing")
def sizing():
    return jsonify(load_json(PATHS["sizing"]))

@app.route("/leverage")
def leverage():
    return jsonify(load_json(PATHS["leverage"]))

@app.route("/history")
def history():
    from pathlib import Path
    import json

    path = Path("/opt/toknclaw/data/snapshots/history.jsonl")

    if not path.exists():
        return jsonify([])

    try:
        with open(path, "r") as f:
            lines = f.readlines()

        # 🔴 FIX: ensure we return last N valid rows
        rows = []
        for line in lines[-500:]:
            try:
                rows.append(json.loads(line))
            except:
                continue

        return jsonify(rows)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/cluster_active")
def cluster_active():
    import json
    from pathlib import Path

    path = Path("/opt/toknclaw/data/analytics/cluster_active.json")

    if not path.exists():
        return {"ok": False, "error": "missing file"}, 404

    with open(path) as f:
        data = json.load(f)

    return data

@app.route("/full_state")
def full_state():
    paper = load_json(PATHS["paper"])
    snapshot = load_json(PATHS["snapshot"])
    decisions_payload = load_json(PATHS["decisions"])
    sizing_payload = load_json(PATHS["sizing"])
    leverage_payload = load_json(PATHS["leverage"])
    performance_payload = load_json(PATHS["performance"])
    clusters_payload = load_json(PATHS["clusters"])

    # 🔴 NORMALIZE CORE DATA (SAFETY)
    portfolio = paper.get("portfolio", {})
    open_positions = list(paper.get("open_positions", {}).values())
    closed_positions = paper.get("closed_positions", [])
    signals = snapshot.get("signals", [])
    market_state = snapshot.get("market_state", {})
    clusters = clusters_payload.get("clusters", [])
    collector_health_payload = load_json(PATHS["health"])

    # 🔴 ARCHIVE SNAPSHOT (NON-BLOCKING)
    try:
        from backend.services.snapshot_archive import append_snapshot

        append_snapshot({
            "snapshot": snapshot,
        })
    except Exception as e:
        # never break API if archive fails
        print(f"[Snapshot Archive Error] {e}")

    # 🔴 RESPONSE (UNCHANGED CONTRACT + TIMESTAMP)
    return jsonify({
        "timestamp": snapshot.get("timestamp"),  # 🔴 NEW (needed for time series)

        "portfolio": portfolio,

        "positions": open_positions,

        "closed_positions": closed_positions,

        "signals": signals,

        "market_state": market_state,

        "clusters": clusters,

        "decisions": decisions_payload,
        "sizing": sizing_payload,
        "leverage": leverage_payload,
        "performance": performance_payload,
        "collector_health": collector_health_payload.get("collector_health", {}),
    })



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8787)
