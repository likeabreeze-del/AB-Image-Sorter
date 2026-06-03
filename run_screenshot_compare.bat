@echo off
setlocal
cd /d "%~dp0"

if exist "dist\screenshot_compare_gui.exe" (
  start "" "dist\screenshot_compare_gui.exe"
  exit /b 0
)

if exist "dist\screenshot_compare.exe" (
  start "" "dist\screenshot_compare.exe" --gui
  exit /b 0
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 screenshot_compare.py --gui
  exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
  python screenshot_compare.py --gui
  exit /b %errorlevel%
)

echo dist\screenshot_compare_gui.exe was not found, and Python was not found.
echo Build the exe first with build_exe.bat, or install Python 3.10+.
pause
exit /b 1
