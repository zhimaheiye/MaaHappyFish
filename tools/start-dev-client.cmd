@echo off
setlocal
set "REPO_ROOT=%~dp0.."
if not exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    echo Missing .venv. See docs/development-environment.md.
    exit /b 1
)
if not exist "%REPO_ROOT%\client_avalonia\MFAAvalonia.exe" (
    echo Missing development client_avalonia\MFAAvalonia.exe.
    exit /b 1
)
set "PATH=%REPO_ROOT%\.venv\Scripts;%PATH%"
set "VIRTUAL_ENV=%REPO_ROOT%\.venv"
start "" /D "%REPO_ROOT%\client_avalonia" "%REPO_ROOT%\client_avalonia\MFAAvalonia.exe"
