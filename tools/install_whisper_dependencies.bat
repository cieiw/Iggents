@echo off
setlocal
cd /d "%~dp0\.."
py -m pip install --upgrade pip
py -m pip install -r requirements-whisper.txt
if errorlevel 1 pause
endlocal
