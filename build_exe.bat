@echo off
setlocal
cd /d "%~dp0"

set PY_CMD=

where py >nul 2>nul
if %errorlevel%==0 set PY_CMD=py -3

if not defined PY_CMD (
  where python >nul 2>nul
  if %errorlevel%==0 set PY_CMD=python
)

if not defined PY_CMD (
  echo Python was not found. Install Python 3.10 or newer first.
  pause
  exit /b 1
)

%PY_CMD% -m PyInstaller.__main__ --onefile --name screenshot_compare screenshot_compare.py
if %errorlevel% neq 0 goto failed

%PY_CMD% -m PyInstaller.__main__ --onefile --windowed --name screenshot_compare_gui screenshot_compare.py
if %errorlevel% neq 0 goto failed

%PY_CMD% -m PyInstaller.__main__ -y --onedir --name screenshot_compare_folder screenshot_compare.py
if %errorlevel% neq 0 goto failed

echo.
echo Build complete:
echo dist\screenshot_compare.exe
echo dist\screenshot_compare_gui.exe
echo dist\screenshot_compare_folder
pause
exit /b 0

:failed
echo.
echo Build failed. Make sure PyInstaller is installed:
echo python -m pip install pyinstaller
pause
exit /b 1
