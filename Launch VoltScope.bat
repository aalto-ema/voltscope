@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" voltscope.py %*
) else (
  py voltscope.py %*
)
if errorlevel 1 pause
