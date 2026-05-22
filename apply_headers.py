#!/usr/bin/env python3
"""
TOKNCLAW — HEADER APPLIER

Safely inserts standardized headers into all Python files.
- Skips files that already contain TOKNCLAW
- Preserves existing code
"""

import os

ROOT_DIR = "/opt/toknclaw"

HEADER = """# ============================================================
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
# MODULE: {module}
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================

"""

def apply_headers():
    for root, _, files in os.walk(ROOT_DIR):
        for file in files:
            if not file.endswith(".py"):
                continue

            path = os.path.join(root, file)

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            if "TOKNCLAW — MARKET INTELLIGENCE ENGINE" in content:
                continue

            module_name = file.replace(".py", "")

            new_content = HEADER.format(module=module_name) + content

            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

            print(f"[HEADER APPLIED] {path}")


if __name__ == "__main__":
    apply_headers()
