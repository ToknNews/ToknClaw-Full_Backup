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
# MODULE: run_agent_optimizer
# PURPOSE: Root-level entrypoint for optimizer v1 recommend-only execution.
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SIGNAL_ENGINE_DIR = ROOT_DIR / "signal_engine"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if str(SIGNAL_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(SIGNAL_ENGINE_DIR))

from signal_engine.agents.optimizer.agent_optimizer import main


if __name__ == "__main__":
    main()
