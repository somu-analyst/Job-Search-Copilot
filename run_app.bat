@echo off
title Job Search Copilot
cd /d "%~dp0"

REM Pinned to 8601 on purpose. The NYSE stock bot's dashboard uses 8502, and
REM Streamlit's default 8501 auto-bumps to 8502 when it's busy - which would
REM make the bot open THIS app instead of its own dashboard. A dedicated port
REM keeps the two apps from ever colliding.

REM If the app is ALREADY running on 8601, don't start a second copy. With an
REM explicit --server.port, Streamlit exits with "port not available" instead
REM of picking another port, so a blind re-launch just flashes an error and
REM closes. Detect it and open the browser to the running app instead.
netstat -ano | findstr ":8601" | findstr "LISTENING" >nul
if %errorlevel%==0 (
  echo.
  echo   Job Search Copilot is already running.
  echo   Opening it at http://localhost:8601 ...
  start "" "http://localhost:8601"
  REM ping as a redirect-safe pause so the message is readable (timeout /t
  REM errors out when stdin is redirected; ping never does).
  ping -n 3 127.0.0.1 >nul
  exit /b 0
)

echo.
echo   Job Search Copilot
echo   ------------------
echo   Starting... your browser will open at http://localhost:8601
echo   Leave THIS window open while you use the app.
echo   Close it (or press Ctrl+C) to shut the app down.
echo.

python -m streamlit run app.py --server.port 8601

echo.
echo   The app has stopped.
pause
