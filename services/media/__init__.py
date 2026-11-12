"""Horizon Veridian Media service package."""

import sys
from pathlib import Path

_MEDIA_ROOT = str(Path(__file__).resolve().parent)
if _MEDIA_ROOT not in sys.path:
    sys.path.insert(0, _MEDIA_ROOT)

