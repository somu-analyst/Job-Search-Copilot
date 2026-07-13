@echo off
title Job Search Copilot - Scan for new jobs
cd /d "%~dp0"

echo.
echo   Scanning for new jobs
echo   ---------------------
echo   Pulls every source, scores each job against your resume, tags its
echo   skills, and resolves a real employer apply link for each one.
echo.
echo   This takes a while - resolving apply links means pulling whole job
echo   boards from each employer. Let it finish.
echo.

python run.py %*

echo.
echo   Scan complete. Open Job Search Copilot to see the new jobs.
pause
