"""Horizon Veridian WorkOS service package."""

import sys
from pathlib import Path

_WORKOS_ROOT = str(Path(__file__).resolve().parent)
if _WORKOS_ROOT not in sys.path:
    sys.path.insert(0, _WORKOS_ROOT)
