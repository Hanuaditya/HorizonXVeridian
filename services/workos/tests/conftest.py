"""Ensure WorkOS root is on sys.path for isolated test execution."""

import sys
from pathlib import Path

WORKOS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]

for p in (str(REPO_ROOT), str(WORKOS_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
