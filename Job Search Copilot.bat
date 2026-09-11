@echo off
REM One entry point: starts the Streamlit server if it isn't already running,
REM then opens the app in its own window (see app_launcher.py for the ladder).
cd /d "%~dp0"
start "" pythonw app_launcher.py
