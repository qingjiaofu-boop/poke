@echo off
cd /d "%~dp0"
if "%~1"=="" (
  python battle_demo.py
) else (
  python battle_demo.py --port "%~1"
)
