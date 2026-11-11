"""Isolate services/media onto sys.path for media service tests."""

import sys
from pathlib import Path

MEDIA_ROOT = Path(__file__).resolve().parents[1]
if str(MEDIA_ROOT) not in sys.path:
    sys.path.insert(0, str(MEDIA_ROOT))
