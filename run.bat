@echo off
cd /d "%~dp0"
if "%~1"=="" (
  python adventure.py
) else (
  python adventure.py %~1
)
