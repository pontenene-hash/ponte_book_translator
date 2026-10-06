@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.11 -m venv .venv
  if errorlevel 1 (
    echo Python 3.11 が必要です。手順書のインストール方法を確認してください。
    pause
    exit /b 1
  )
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo インストールに失敗しました。通信環境を確認してください。
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m streamlit run app.py
pause
