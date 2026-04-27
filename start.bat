@echo off
REM ─────────────────────────────────────────────
REM  APEX Trading Agent — Start Everything (Windows)
REM ─────────────────────────────────────────────

set ROOT=%~dp0
set BACKEND=%ROOT%backend
set FRONTEND=%ROOT%frontend

echo.
echo   ⚡ APEX AI Trading Agent
echo   ─────────────────────────
echo.

REM Check .env
if not exist "%BACKEND%\.env" (
    echo   ERROR: backend\.env not found.
    pause
    exit /b 1
)

REM Install Python deps
echo   Installing Python dependencies...
cd /d "%BACKEND%"
python -m pip install -r requirements.txt -q

REM Install Node deps
echo   Installing Node dependencies...
cd /d "%FRONTEND%"
if not exist "node_modules" (
    npm install --silent
)

REM Start backend in new window
echo.
echo   Starting backend  on http://localhost:8000
start "APEX Backend" cmd /k "cd /d %BACKEND% && python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload"

REM Wait a moment
timeout /t 3 /nobreak >nul

REM Start frontend in new window
echo   Starting frontend on http://localhost:3000
start "APEX Frontend" cmd /k "cd /d %FRONTEND% && npm run dev"

echo.
echo   Both servers are starting in separate windows.
echo   Open http://localhost:3000 in your browser.
echo.
pause
