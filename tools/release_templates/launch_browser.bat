@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "BROWSER_EXE="
set "TARGET_URL=https://game.maj-soul.com/"
set "CONFIG_PATH=%~dp0config\runtime_config.bat"
set "PROXY_HOST=127.0.0.1"
set "PROXY_PORT=8080"

if exist "%CONFIG_PATH%" call "%CONFIG_PATH%"

if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
) else if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
)

if not defined BROWSER_EXE (
    echo [ERROR] Chrome or Edge was not found.
    echo Please install Chrome or Edge first, or open the browser manually with:
    echo   --proxy-server=http://%PROXY_HOST%:%PROXY_PORT%
    exit /b 1
)

echo ==================================================
echo              Launch Majsoul Browser
echo ==================================================
echo This launcher reuses your normal browser profile so the Majsoul login
echo state can be preserved.
echo.
echo To make sure the proxy argument takes effect, please close existing
echo Chrome or Edge windows first.
echo.
choice /M "Continue launching the browser with proxy %PROXY_HOST%:%PROXY_PORT%"
if errorlevel 2 exit /b 0

echo [INFO] Launching browser with proxy %PROXY_HOST%:%PROXY_PORT% and existing user data
start "" "%BROWSER_EXE%" ^
  --proxy-server=http://%PROXY_HOST%:%PROXY_PORT% ^
  --new-window "%TARGET_URL%"

exit /b 0
