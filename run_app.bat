@echo off
title Job Search Copilot
cd /d "%~dp0"

echo.
echo   Job Search Copilot
echo   ------------------
echo   Starting... your browser will open at http://localhost:8501
echo   Leave THIS window open while you use the app.
echo   Close it (or press Ctrl+C) to shut the app down.
echo.

python -m streamlit run app.py

echo.
echo   The app has stopped.
pause
