"""
Claude Takeover Module

This module provides functionality to continue phone automation with Claude
from existing context, without needing a backend server.

Main components:
- ADBTakeover: Android device takeover agent (uses ADB)
- HDCTakeover: HarmonyOS device takeover agent (uses HDC)
- ModelClient: Direct Claude API client without backend dependency
"""

from claude_takeover.adb_takeover import ADBTakeover
from claude_takeover.hdc_takeover import HDCTakeover

__all__ = ["ADBTakeover", "HDCTakeover"]
