@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "BUILDER=%~dp0tools\build_release.py"
set "PYTHON_CMD="

if not exist "%BUILDER%" (
    echo [ERROR] Missing release builder: %BUILDER%
    exit /b 1
)

if exist "%~dp0Crawler\.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0Crawler\.venv\Scripts\python.exe"
    goto run
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=py -3"
    goto run
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    goto run
)

echo [ERROR] Python 3 was not found.
exit /b 1

:run
%PYTHON_CMD% "%BUILDER%" %*
exit /b %errorlevel%
