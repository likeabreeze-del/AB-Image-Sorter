@echo off
setlocal
cd /d "%~dp0"

set EXE=screenshot_compare.exe
if exist "dist\screenshot_compare.exe" set EXE=dist\screenshot_compare.exe

echo Screenshot compare tool
echo.
echo This launcher keeps the window open and writes run_log.txt.
echo If it fails on a teammate's computer, ask them to send run_log.txt
echo and screenshot_compare_error.log.
echo.

"%EXE%" --gui > run_log.txt 2>&1
set EXITCODE=%errorlevel%

echo.
echo Exit code: %EXITCODE%
echo Exit code: %EXITCODE%>> run_log.txt

if exist screenshot_compare_error.log (
  echo.
  echo Error log was created: screenshot_compare_error.log
)

echo.
pause
exit /b %EXITCODE%
