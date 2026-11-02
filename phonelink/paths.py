"""Filesystem locations."""

from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys.executable).resolve().parent
else:
    APP_ROOT = Path(__file__).resolve().parents[1]

UI_DIR = APP_ROOT / "ui"
