@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo 先に start_windows.bat を一度実行してください。
  pause
  exit /b 1
)
.venv\Scripts\python.exe google_setup.py
pause
