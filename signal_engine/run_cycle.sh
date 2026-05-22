#!/usr/bin/env bash
set -euo pipefail

cd /opt/toknclaw/signal_engine
source venv/bin/activate
python run_snapshot.py
