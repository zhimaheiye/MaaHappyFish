@echo off
chcp 65001 >nul
title MaaHappyFish 测试日志收集器

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect_test_report.ps1"
set "collector_exit=%ERRORLEVEL%"

if not "%collector_exit%"=="0" (
    echo.
    echo 收集失败。请先关闭 MFAAvalonia，并确认程序至少运行过一次。
)

echo.
pause
exit /b %collector_exit%
