@echo off
REM One entry point: starts the Streamlit server if it isn't already running,
REM then opens the app in its own window (see app_launcher.py for the ladder).
REM Uses the venv at C:\jsc-venv, not system Python -- that's where BM25 +
REM sentence-transformers (semantic ATS scoring) actually live. System
REM Python couldn't install them at all: torch's install path exceeded
REM Windows' 260-char limit under the deeply-nested Windows Store Python
REM location, so a separate short-path venv was created instead of touching
REM any system-wide settings.
cd /d "%~dp0"
if exist "C:\jsc-venv\Scripts\pythonw.exe" (
    start "" "C:\jsc-venv\Scripts\pythonw.exe" app_launcher.py
) else (
    start "" pythonw app_launcher.py
)
