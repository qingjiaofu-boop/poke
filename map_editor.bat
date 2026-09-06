@echo off
set "MAP_NAME=%~1"
if "%MAP_NAME%"=="" set "MAP_NAME=home"
cd /d "%~dp0"
python tools\map_editor.py %MAP_NAME%
pause
