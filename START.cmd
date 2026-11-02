@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo First run: py -3 -m venv .venv
  echo Then: .venv\Scripts\python -m pip install -e .
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m solsol serve
