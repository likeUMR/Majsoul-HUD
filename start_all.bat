@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "ALGO_DIR=%ROOT%Algorithm\mahjong-cpp-master"
set "ALGO_LAUNCHER=%ROOT%tools\launchers\algorithm_backend_launcher.py"
set "CRAWLER_DIR=%ROOT%Crawler"
set "CRAWLER_BAT=%CRAWLER_DIR%\run.bat"
set "PORTABLE_PY_DIR=%ROOT%runtime\python"
set "PORTABLE_SITE_PACKAGES=%ROOT%runtime\site-packages"
set "RUNTIME_STATE_DIR=%ROOT%.runtime"
set "ALGO_PID_PATH=%RUNTIME_STATE_DIR%\algorithm_backend.pid"
set "ALGO_LOG_PATH=%RUNTIME_STATE_DIR%\algorithm_backend_launcher.log"
set "CONFIG_PATH=%ROOT%config\runtime_config.bat"
set "CRAWLER_PY=%CRAWLER_DIR%\.venv\Scripts\python.exe"
set "ALGO_HOST=127.0.0.1"
set "ALGO_PORT=50000"
set "PROXY_HOST=127.0.0.1"
set "PROXY_PORT=8080"
set "HUD_EXTRA_SCALE=1.0"
set "SERVER_PID="
set "SERVER_STARTED=0"
set "CERT_SOURCE=%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.cer"
set "CERT_FALLBACK_DIR=%ROOT%cert"
set "CERT_FALLBACK_PATH=%CERT_FALLBACK_DIR%\mitmproxy-ca-cert.cer"
set "CERT_GUIDE_PATH=%ROOT%CERT_INSTALL_GUIDE.txt"
set "PORTABLE_MODE="

if exist "%CONFIG_PATH%" call "%CONFIG_PATH%"
set "SERVER_HOST=%ALGO_HOST%"
set "SERVER_PORT=%ALGO_PORT%"
set "MAJSOUL_ALGO_HOST=%ALGO_HOST%"
set "MAJSOUL_ALGO_PORT=%ALGO_PORT%"
set "MAJSOUL_ALGO_URL=http://%ALGO_HOST%:%ALGO_PORT%"
set "MAJSOUL_PROXY_HOST=%PROXY_HOST%"
set "MAJSOUL_PROXY_PORT=%PROXY_PORT%"
set "MAJSOUL_HUD_EXTRA_SCALE=%HUD_EXTRA_SCALE%"

if exist "%PORTABLE_PY_DIR%\python.exe" if exist "%PORTABLE_SITE_PACKAGES%" (
    set "PORTABLE_MODE=1"
    set "CRAWLER_PY=%PORTABLE_PY_DIR%\python.exe"
    call :configure_portable_python
)

if not exist "%ALGO_LAUNCHER%" (
    echo [ERROR] Missing algorithm launcher: %ALGO_LAUNCHER%
    exit /b 1
)

if not exist "%CRAWLER_BAT%" (
    echo [ERROR] Missing crawler launcher: %CRAWLER_BAT%
    exit /b 1
)

echo ==================================================
echo        Majsoul Crawler + Algorithm Start
echo ==================================================
echo.

if not defined PORTABLE_MODE if not exist "%CRAWLER_DIR%\.venv\Scripts\mitmdump.exe" (
    echo [INFO] Crawler dependencies are missing. Installing first...
    call "%CRAWLER_BAT%" 1
    if errorlevel 1 (
        echo [ERROR] Failed to install crawler dependencies.
        exit /b 1
    )
)

if not exist "%CRAWLER_PY%" (
    echo [ERROR] Missing crawler Python executable: %CRAWLER_PY%
    exit /b 1
)

"%CRAWLER_PY%" -c "import requests" >nul 2>nul
if errorlevel 1 (
    if defined PORTABLE_MODE (
        echo [ERROR] Portable Python runtime is incomplete.
        echo [ERROR] Please rebuild the release package.
        exit /b 1
    )
    echo [INFO] requests is missing. Updating crawler dependencies...
    call "%CRAWLER_BAT%" 1
    if errorlevel 1 (
        echo [ERROR] Failed to update crawler dependencies.
        exit /b 1
    )
)

call :ensure_cert_ready
if errorlevel 1 exit /b 1

call :cleanup_stale_runtime

call :wait_port 300
if not errorlevel 1 (
    echo [INFO] Mahjong algorithm server is already running on %SERVER_HOST%:%SERVER_PORT%
) else (
    echo [INFO] Starting stable mahjong-cpp backend launcher...
    for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$p = Start-Process -FilePath $env:CRAWLER_PY -ArgumentList @($env:ALGO_LAUNCHER, 'serve', '--port', $env:SERVER_PORT) -WorkingDirectory $env:ROOT -PassThru -WindowStyle Hidden; $p.Id"`) do set "SERVER_PID=%%I"
    if not defined SERVER_PID (
        echo [ERROR] Failed to start algorithm launcher.
        exit /b 1
    )
    set "SERVER_STARTED=1"

    call :wait_port 30000
    if errorlevel 1 (
        echo [ERROR] mahjong-cpp backend did not become ready on %SERVER_HOST%:%SERVER_PORT%
        call :show_backend_log_tail
        if defined SERVER_PID taskkill /PID %SERVER_PID% /T /F >nul 2>nul
        if exist "%ALGO_PID_PATH%" del /f /q "%ALGO_PID_PATH%" >nul 2>nul
        exit /b 1
    )
)

echo [INFO] Starting crawler listener...
echo [INFO] Algorithm URL: http://%SERVER_HOST%:%SERVER_PORT%
echo [INFO] Proxy address: %PROXY_HOST%:%PROXY_PORT%
echo.

call "%CRAWLER_BAT%" 2
set "CRAWLER_EXIT=%errorlevel%"

if "%SERVER_STARTED%"=="1" if defined SERVER_PID (
    echo.
    echo [INFO] Stopping algorithm launcher...
    taskkill /PID %SERVER_PID% /T /F >nul 2>nul
    if exist "%ALGO_PID_PATH%" del /f /q "%ALGO_PID_PATH%" >nul 2>nul
)

exit /b %CRAWLER_EXIT%

:cleanup_stale_runtime
echo [INFO] Cleaning stale runtime processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$targets = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and (($_.CommandLine -like '*algorithm_backend_launcher.py*serve --port %SERVER_PORT%*') -or ($_.CommandLine -like '*nanikiru.exe %SERVER_PORT%*') -or (($_.CommandLine -like '*addons.py*') -and (($_.CommandLine -like '*--listen-port %PROXY_PORT%*') -or ($_.CommandLine -like '*-p %PROXY_PORT%*'))) -or ($_.CommandLine -like '*hud.py --majsoul-hud*') -or ($_.CommandLine -like '*--majsoul-hud*')) }; foreach ($p in $targets) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {} }" >nul 2>nul
timeout /t 1 >nul 2>nul
exit /b 0

:configure_portable_python
set "PYTHONHOME=%PORTABLE_PY_DIR%"
set "PYTHONPATH=%PORTABLE_SITE_PACKAGES%"
set "PYTHONNOUSERSITE=1"
exit /b 0

:ensure_cert_ready
echo [INFO] Checking mitmproxy certificate...
call :ensure_cert_generated
if errorlevel 1 (
    echo [ERROR] Failed to prepare the local mitmproxy certificate.
    echo [ERROR] Please check whether the crawler runtime is complete.
    exit /b 1
)

call :cert_is_installed
if not errorlevel 1 (
    echo [INFO] mitmproxy certificate is already installed.
    exit /b 0
)

echo [INFO] Certificate is not installed. Trying automatic import...
call :try_install_cert
if not errorlevel 1 (
    echo [INFO] Certificate installed successfully.
    exit /b 0
)

echo [WARN] Automatic certificate import was blocked or failed.
echo [WARN] Preparing manual fallback files...
call :prepare_cert_fallback
echo.
echo [ACTION REQUIRED] Please follow the opened guide, install the certificate,
echo [ACTION REQUIRED] then run start_all.bat again.
exit /b 1

:ensure_cert_generated
if exist "%CERT_SOURCE%" exit /b 0
echo [INFO] Generating local mitmproxy certificate...
"%CRAWLER_PY%" -c "import os; from mitmproxy.certs import CertStore; CertStore.from_store(os.path.expanduser(r'~/.mitmproxy'), 'mitmproxy', 2048)" >nul 2>nul
if exist "%CERT_SOURCE%" exit /b 0
exit /b 1

:cert_is_installed
if not exist "%CERT_SOURCE%" exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($env:CERT_SOURCE); $thumb = $cert.Thumbprint; $storePath = 'Cert:\CurrentUser\Root'; $exists = Get-ChildItem $storePath | Where-Object { $_.Thumbprint -eq $thumb }; if ($exists) { exit 0 } else { exit 1 }" >nul 2>nul
exit /b %errorlevel%

:try_install_cert
if not exist "%CERT_SOURCE%" exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($env:CERT_SOURCE); $thumb = $cert.Thumbprint; $storePath = 'Cert:\CurrentUser\Root'; $exists = Get-ChildItem $storePath | Where-Object { $_.Thumbprint -eq $thumb }; if ($exists) { exit 0 }; Import-Certificate -FilePath $env:CERT_SOURCE -CertStoreLocation $storePath | Out-Null; exit 0" >nul 2>nul
exit /b %errorlevel%

:prepare_cert_fallback
if not exist "%CERT_FALLBACK_DIR%" mkdir "%CERT_FALLBACK_DIR%" >nul 2>nul
copy /y "%CERT_SOURCE%" "%CERT_FALLBACK_PATH%" >nul 2>nul
> "%CERT_GUIDE_PATH%" (
    echo AI_Mahjong Certificate Manual Install Guide / AI_Mahjong 证书手动安装说明
    echo ============================================================================
    echo.
    echo Automatic certificate installation was blocked or failed on this PC.
    echo 当前电脑阻止了自动导入证书，或者自动导入失败。
    echo.
    echo Certificate file / 证书文件:
    echo %CERT_FALLBACK_PATH%
    echo.
    echo Steps / 操作步骤:
    echo 1. Double-click the certificate file above.
    echo 1. 双击上面的证书文件。
    echo 2. Click "Install Certificate...".
    echo 2. 点击“安装证书...”。
    echo 3. Choose "Current User".
    echo 3. 选择“当前用户”。
    echo 4. Choose "Place all certificates in the following store".
    echo 4. 选择“将所有的证书都放入下列存储”。
    echo 5. Select "Trusted Root Certification Authorities".
    echo 5. 选择“受信任的根证书颁发机构”。
    echo 6. Finish the wizard, then run start_all.bat again.
    echo 6. 完成向导后，再重新运行 start_all.bat。
    echo.
    echo Note / 说明:
    echo - This certificate was generated on this PC for this local mitmproxy instance.
    echo - 这份证书是当前电脑为本地 mitmproxy 自动生成的匹配证书。
)
start "" notepad "%CERT_GUIDE_PATH%" >nul 2>nul
start "" "%CERT_FALLBACK_PATH%" >nul 2>nul
explorer /select,"%CERT_FALLBACK_PATH%" >nul 2>nul
exit /b 0

:show_backend_log_tail
if not exist "%ALGO_LOG_PATH%" exit /b 0
echo.
echo [INFO] Backend launcher log tail:
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -Path \"$env:ALGO_LOG_PATH\" -Tail 20" 2>nul
exit /b 0

:wait_port
powershell -NoProfile -Command "$timeout = [int]%~1; $deadline = (Get-Date).AddMilliseconds($timeout); do { try { $client = New-Object Net.Sockets.TcpClient; $iar = $client.BeginConnect($env:SERVER_HOST, [int]$env:SERVER_PORT, $null, $null); $ok = $iar.AsyncWaitHandle.WaitOne(300); if ($ok -and $client.Connected) { $client.EndConnect($iar); $client.Close(); exit 0 } $client.Close() } catch {} Start-Sleep -Milliseconds 200 } while ((Get-Date) -lt $deadline); exit 1" >nul 2>nul
exit /b %errorlevel%
