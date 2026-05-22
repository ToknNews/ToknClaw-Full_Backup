#!/usr/bin/env python3
"""
🦞 TOKNCLAW BOOTSTRAP
Ensures consistent module imports across the system.
"""

import sys

# ensure root path
ROOT = "/opt/toknclaw"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ---------------------------------------------------
# 🔥 FORCE SINGLE REGISTRY OBJECT
# ---------------------------------------------------

import signal_engine.collectors.registry as se_registry

# alias ALL legacy imports to the same module
sys.modules["collectors.registry"] = se_registry
