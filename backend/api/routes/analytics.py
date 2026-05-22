from flask import Blueprint, jsonify
from pathlib import Path
import json

analytics_routes = Blueprint("analytics_routes", __name__)

BASE = Path("/opt/toknclaw")

PATHS = {
    "paper": BASE / "data/paper_trading_state.json",
    "snapshot": BASE / "data/snapshots/latest_snapshot_trading.json",
    "decisions": BASE / "data/analytics/strategy_decisions.json",
    "sizing": BASE / "data/analytics/trade_sizing.json",
    "leverage": BASE / "data/analytics/trade_leverage.json",
    "performance": BASE / "data/analytics/strategy_performance.json"
}

def load_json(path):
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}

@analytics_routes.route("/health")
def health():
    return jsonify({"status": "ok"})

@analytics_routes.route("/portfolio")
def portfolio():
    return jsonify(load_json(PATHS["paper"]).get("portfolio", {}))

@analytics_routes.route("/open_positions")
def open_positions():
    return jsonify(list(load_json(PATHS["paper"]).get("open_positions", {}).values()))

@analytics_routes.route("/sizing")
def sizing():
    return jsonify(load_json(PATHS["sizing"]))

@analytics_routes.route("/leverage")
def leverage():
    return jsonify(load_json(PATHS["leverage"]))

@analytics_routes.route("/decisions")
def decisions():
    return jsonify(load_json(PATHS["decisions"]))

@analytics_routes.route("/full_state")
def full_state():
    return jsonify({
        "portfolio": load_json(PATHS["paper"]).get("portfolio", {}),
        "positions": list(load_json(PATHS["paper"]).get("open_positions", {}).values()),
        "signals": load_json(PATHS["snapshot"]).get("trade_signals", {}),
        "decisions": load_json(PATHS["decisions"]),
        "sizing": load_json(PATHS["sizing"]),
        "leverage": load_json(PATHS["leverage"])
    })
