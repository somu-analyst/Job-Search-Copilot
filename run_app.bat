@echo off
title Job Search Copilot
cd /d "%~dp0"

echo.
echo   Job Search Copilot
echo   ------------------
echo   Starting... your browser will open at http://localhost:8601
echo   Leave THIS window open while you use the app.
echo   Close it (or press Ctrl+C) to shut the app down.
echo.

REM Pinned to 8601 on purpose. The NYSE stock bot's dashboard uses 8502, and
REM Streamlit's default 8501 auto-bumps to 8502 when it's busy — which would
REM make the bot open THIS app instead of its own dashboard. A dedicated port
REM keeps the two apps from ever colliding.
python -m streamlit run app.py --server.port 8601

echo.
echo   The app has stopped.
pause
