@echo off
setlocal
cd /d "%~dp0"
py -m pip install --upgrade pyinstaller customtkinter pillow uiautomator2 playwright
py -m pip install -r requirements-whisper.txt
py -m PyInstaller --noconfirm --clean IGGen.spec
if errorlevel 1 pause
endlocal
