@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
set PORT=5003
.venv\Scripts\python.exe app.py
