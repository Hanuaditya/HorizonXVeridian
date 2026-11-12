#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export DEMO_MODE=true
export NEXT_PUBLIC_DEMO_MODE=true
export APP_ENV=development
export PYTHONUNBUFFERED=1

echo "==============================================================="
echo "  Horizon Veridian x Gnani AI — Unified Demo Launcher (Unix)"
echo "==============================================================="
echo "  WorkOS Hub       : http://localhost:3000/workos"
echo "  Meetings Hub     : http://localhost:3000/meetings"
echo "  Admin & Maps     : http://localhost:3000/admin"
echo "  Media Health     : http://localhost:5001/health"
echo "  WorkOS Health    : http://localhost:8000/health"
echo "==============================================================="

trap 'kill 0' EXIT

(cd "$ROOT_DIR/services/media" && python app.py) &
(cd "$ROOT_DIR/services/workos" && python -m uvicorn api.main:app --host 0.0.0.0 --port 8000) &
(cd "$ROOT_DIR/apps/web" && npm run dev) &

wait

