@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
for %%I in ("%ROOT%..\..") do set "PROJECT_ROOT=%%~fI"
set "LAUNCHER=%PROJECT_ROOT%\tools\launchers\algorithm_backend_launcher.py"
set "CONFIG_PATH=%PROJECT_ROOT%\config\runtime_config.bat"
set "ALGO_PORT=50000"

if exist "%CONFIG_PATH%" call "%CONFIG_PATH%"

if not exist "%LAUNCHER%" (
    echo [ERROR] Missing stable launcher: %LAUNCHER%
    exit /b 1
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 "%LAUNCHER%" serve --port %ALGO_PORT%
    exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    python "%LAUNCHER%" serve --port %ALGO_PORT%
    exit /b %errorlevel%
)

echo [ERROR] Python 3 was not found.
echo Please install Python 3.10+ first, or launch via top-level start_all.bat.
exit /b 1

endlocal
