@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
for %%I in ("%ROOT%..") do set "PROJECT_ROOT=%%~fI"
set "VENV_DIR=.venv"
set "TUNA_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
set "AUTO_MODE="
set "PORTABLE_ROOT=%PROJECT_ROOT%"
set "PORTABLE_PY_DIR=%PORTABLE_ROOT%\runtime\python"
set "PORTABLE_SITE_PACKAGES=%PORTABLE_ROOT%\runtime\site-packages"
set "PORTABLE_PY=%PORTABLE_PY_DIR%\python.exe"
set "PORTABLE_PYW=%PORTABLE_PY_DIR%\pythonw.exe"
set "CONFIG_PATH=%PROJECT_ROOT%\config\runtime_config.bat"
set "ALGO_HOST=127.0.0.1"
set "ALGO_PORT=50000"
set "PROXY_HOST=127.0.0.1"
set "PROXY_PORT=8080"
set "HUD_EXTRA_SCALE=1.0"
set "PORTABLE_MODE="

if exist "%CONFIG_PATH%" call "%CONFIG_PATH%"
set "MAJSOUL_ALGO_HOST=%ALGO_HOST%"
set "MAJSOUL_ALGO_PORT=%ALGO_PORT%"
set "MAJSOUL_ALGO_URL=http://%ALGO_HOST%:%ALGO_PORT%"
set "MAJSOUL_PROXY_HOST=%PROXY_HOST%"
set "MAJSOUL_PROXY_PORT=%PROXY_PORT%"
set "MAJSOUL_HUD_EXTRA_SCALE=%HUD_EXTRA_SCALE%"

if exist "%PORTABLE_PY%" if exist "%PORTABLE_SITE_PACKAGES%" (
    set "PORTABLE_MODE=1"
)

if "%~1"=="1" (
    set "AUTO_MODE=1"
    goto install
)
if "%~1"=="2" (
    set "AUTO_MODE=1"
    goto run
)
if "%~1"=="3" (
    set "AUTO_MODE=1"
    goto guide
)
if "%~1"=="4" (
    goto end
)

:menu
cls
echo ==================================================
echo         Majsoul Minimal CLI Listener
echo ==================================================
echo 1. Install or update dependencies
echo 2. Start listener
echo 3. Show proxy and certificate guide
echo 4. Exit
echo.
set /p "CHOICE=Select [1-4]: "

if "%CHOICE%"=="1" goto install
if "%CHOICE%"=="2" goto run
if "%CHOICE%"=="3" goto guide
if "%CHOICE%"=="4" goto end
goto menu

:resolve_python
if defined PORTABLE_MODE (
    call :configure_portable_python
    set "PYTHON_CMD=%PORTABLE_PY%"
    set "PYTHONW_CMD=%PORTABLE_PYW%"
    goto :eof
)

set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE="
where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=py -3"
    set "PYTHONW_CMD="
    goto :eof
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    set "PYTHONW_CMD="
    goto :eof
)

echo Python 3 was not found. Please install Python 3.10+ first.
if defined AUTO_MODE exit /b 1
pause
exit /b 1

:configure_portable_python
set "PYTHONHOME=%PORTABLE_PY_DIR%"
set "PYTHONPATH=%PORTABLE_SITE_PACKAGES%"
set "PYTHONNOUSERSITE=1"
exit /b 0

:install
if defined PORTABLE_MODE (
    echo.
    echo Dependencies are already bundled in this portable release.
    if defined AUTO_MODE goto end
    pause
    goto menu
)

call :resolve_python
if %errorlevel% neq 0 goto end

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Failed to create virtual environment.
        if defined AUTO_MODE exit /b 1
        pause
        goto menu
    )
)

call "%VENV_DIR%\Scripts\activate.bat"
echo Upgrading pip...
python -m pip install --upgrade pip -i %TUNA_INDEX%
if %errorlevel% neq 0 (
    echo Failed to upgrade pip.
    if defined AUTO_MODE exit /b 1
    pause
    goto menu
)

echo Installing requirements with Tsinghua mirror...
python -m pip install -r requirements.txt -i %TUNA_INDEX%
if %errorlevel% neq 0 (
    echo Failed to install requirements.
    if defined AUTO_MODE exit /b 1
    pause
    goto menu
)

echo.
echo Dependencies are ready.
if defined AUTO_MODE goto end
pause
goto menu

:run
call :resolve_python
if %errorlevel% neq 0 goto end

if defined PORTABLE_MODE goto run_portable

if not exist "%VENV_DIR%\Scripts\mitmdump.exe" (
    echo Dependencies are not installed yet.
    echo Please select option 1 first.
    if defined AUTO_MODE exit /b 1
    pause
    goto menu
)

"%VENV_DIR%\Scripts\python.exe" -c "import requests" >nul 2>nul
if %errorlevel% neq 0 (
    echo Missing Python dependency: requests
    echo Please select option 1 first.
    if defined AUTO_MODE exit /b 1
    pause
    goto menu
)

call "%VENV_DIR%\Scripts\activate.bat"
echo.
echo Proxy address: %PROXY_HOST%:%PROXY_PORT%
echo Cleaning old HUD processes...
powershell -NoProfile -Command "$targets = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -like '*--majsoul-hud*' -or $_.CommandLine -like '*hud.py*') }; foreach ($p in $targets) { try { Start-Process -FilePath taskkill.exe -ArgumentList @('/PID', $p.ProcessId, '/T', '/F') -WindowStyle Hidden -Wait } catch {} }" >nul 2>nul
if exist "hud_debug.log" del /f /q "hud_debug.log" >nul 2>nul
echo Starting HUD overlay...
if exist "%VENV_DIR%\Scripts\pythonw.exe" (
    start "" "%VENV_DIR%\Scripts\pythonw.exe" hud.py --majsoul-hud
) else (
    start "" "%VENV_DIR%\Scripts\python.exe" hud.py --majsoul-hud
)
echo After the listener starts, open Majsoul in a browser that uses this proxy.
echo.
"%VENV_DIR%\Scripts\mitmdump.exe" -q --flow-detail 0 -s addons.py --listen-host %PROXY_HOST% --listen-port %PROXY_PORT%
echo.
if defined AUTO_MODE goto end
pause
goto menu

:run_portable
"%PYTHON_CMD%" -c "import requests, mitmproxy" >nul 2>nul
if %errorlevel% neq 0 (
    echo Portable Python runtime is incomplete.
    echo Please rebuild the release package.
    if defined AUTO_MODE exit /b 1
    pause
    goto menu
)

echo.
echo Proxy address: %PROXY_HOST%:%PROXY_PORT%
echo Cleaning old HUD processes...
powershell -NoProfile -Command "$targets = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -like '*--majsoul-hud*' -or $_.CommandLine -like '*hud.py*') }; foreach ($p in $targets) { try { Start-Process -FilePath taskkill.exe -ArgumentList @('/PID', $p.ProcessId, '/T', '/F') -WindowStyle Hidden -Wait } catch {} }" >nul 2>nul
if exist "hud_debug.log" del /f /q "hud_debug.log" >nul 2>nul
echo Starting HUD overlay...
if exist "%PYTHONW_CMD%" (
    start "" "%PYTHONW_CMD%" hud.py --majsoul-hud
) else (
    start "" "%PYTHON_CMD%" hud.py --majsoul-hud
)
echo After the listener starts, open Majsoul in a browser that uses this proxy.
echo.
"%PYTHON_CMD%" -c "from mitmproxy.tools.main import mitmdump; mitmdump()" -q --flow-detail 0 -s addons.py --listen-host %PROXY_HOST% --listen-port %PROXY_PORT%
echo.
if defined AUTO_MODE goto end
pause
goto menu

:guide
cls
echo ==================================================
echo                Proxy Guide
echo ==================================================
echo 1. Start the listener with option 2.
echo 2. Set your browser or system proxy to %PROXY_HOST%:%PROXY_PORT%.
echo 3. While the listener is running, visit http://mitm.it in that proxied browser.
echo 4. Download the Windows certificate and install it to:
echo    Trusted Root Certification Authorities
echo 5. Restart the browser, then open https://game.maj-soul.com/
echo.
echo Notes:
echo - This project captures Majsoul WebSocket traffic, not screenshots.
echo - Without the mitmproxy certificate, HTTPS and WSS traffic cannot be decrypted.
echo - If you only want to proxy Chrome, create a dedicated shortcut and append:
echo   --proxy-server=http://%PROXY_HOST%:%PROXY_PORT%
echo.
if defined AUTO_MODE goto end
pause
goto menu

:end
endlocal
