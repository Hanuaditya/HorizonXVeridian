@echo off
setlocal
cd /d "%~dp0\.."

set DEMO_MODE=true
set NEXT_PUBLIC_DEMO_MODE=true
set APP_ENV=development
set PYTHONUNBUFFERED=1

echo ===============================================================
echo   Horizon Veridian x Gnani AI -- Unified Demo Launcher (Windows)
echo ===============================================================
echo   WorkOS Hub       : http://localhost:3000/workos
echo   Meetings Hub     : http://localhost:3000/meetings
echo   Admin ^& Maps     : http://localhost:3000/admin
echo   Media Health     : http://localhost:5001/health
echo   WorkOS Health    : http://localhost:8000/health
echo ===============================================================

start "Horizon Media (5001)" cmd /k "cd /d %CD%\services\media && set DEMO_MODE=true && python app.py"
start "Horizon WorkOS (8000)" cmd /k "cd /d %CD%\services\workos && set DEMO_MODE=true && python -m uvicorn api.main:app --host 0.0.0.0 --port 8000"
start "Horizon Web (3000)" cmd /k "cd /d %CD%\apps\web && set DEMO_MODE=true && set NEXT_PUBLIC_DEMO_MODE=true && npm run dev"

echo Services launched in dedicated windows. Open http://localhost:3000/workos in your browser.

