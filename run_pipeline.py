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
# MODULE: run_pipeline
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================

TOKNCLAW — PIPELINE RUNNER

Unified execution entrypoint for ToknClaw system.
"""

import argparse
import time
import traceback
import sys
import os

# ============================================================
# PATH SETUP (CRITICAL — DO NOT CHANGE)
# ============================================================

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SIGNAL_ENGINE_DIR = os.path.join(ROOT_DIR, "signal_engine")

sys.path.insert(0, "/opt/toknclaw/signal_engine")
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, SIGNAL_ENGINE_DIR)

# Legacy import compatibility
import signal_engine.pipeline as pipeline
sys.modules["pipeline"] = pipeline

# ============================================================
# IMPORT ENTRYPOINT
# ============================================================

from signal_engine.run_snapshot import main as run_snapshot

# ============================================================
# RUNNER
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="ToknClaw Pipeline Runner")

    parser.add_argument(
        "--mode",
        choices=["full", "snapshot"],
        default="full",
        help="Execution mode"
    )

    parser.add_argument(
        "--stage",
        type=str,
        help="(Future) Run specific stage"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output"
    )

    args = parser.parse_args()

    start_time = time.time()

    print("\n============================================================")
    print(" 🦞 TOKNCLAW PIPELINE RUNNER")
    print("============================================================\n")

    try:
        # --------------------------------------------------------
        # FULL SNAPSHOT
        # --------------------------------------------------------
        if args.mode in ["full", "snapshot"]:
            print("[RUNNER] Executing full snapshot pipeline...\n")
            run_snapshot()

        # --------------------------------------------------------
        # FUTURE: STAGE EXECUTION
        # --------------------------------------------------------
        if args.stage:
            print(f"[RUNNER] Stage execution not yet implemented: {args.stage}")

        duration = round(time.time() - start_time, 2)

        print("\n============================================================")
        print(f"[RUNNER] COMPLETE — {duration}s")
        print("============================================================\n")

    except Exception:
        print("\n============================================================")
        print("[RUNNER] FAILED")
        print("============================================================\n")

        traceback.print_exc()


if __name__ == "__main__":
    main()
