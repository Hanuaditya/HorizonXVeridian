"""Isolate services/media onto sys.path and shield unit tests from live credentials."""

import os
import sys
from pathlib import Path

MEDIA_ROOT = Path(__file__).resolve().parents[1]
if str(MEDIA_ROOT) not in sys.path:
    sys.path.insert(0, str(MEDIA_ROOT))

for _k, _v in {
    "APP_ENV": "development",
    "DEMO_MODE": "true",
    "SUPABASE_URL": "",
    "SUPABASE_SERVICE_ROLE_KEY": "",
    "SUPABASE_KEY": "",
    "GNANI_API_KEY": "",
    "GEMINI_API_KEY": "",
    "CLOUDINARY_CLOUD_NAME": "",
}.items():
    os.environ[_k] = _v
