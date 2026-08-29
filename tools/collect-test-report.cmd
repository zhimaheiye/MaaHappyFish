@echo off
title MaaHappyFish Test Log Collector

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect_test_report.ps1"
set "collector_exit=%ERRORLEVEL%"

if not "%collector_exit%"=="0" (
    echo.
    echo Collection failed. Close MFAAvalonia and make sure MaaHappyFish has run at least once.
)

echo.
pause
exit /b %collector_exit%
