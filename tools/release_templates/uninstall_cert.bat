@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "CERT_PATH=%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.cer"
set "GUIDE_PATH=%~dp0CERT_UNINSTALL_GUIDE.txt"

if not exist "%CERT_PATH%" (
    echo [ERROR] mitmproxy certificate file was not found:
    echo   %CERT_PATH%
    echo.
    echo Cannot determine which certificate to remove automatically.
    exit /b 1
)

echo ==================================================
echo            Uninstall mitmproxy Certificate
echo ==================================================
echo This will remove the mitmproxy CA certificate from:
echo   Current User ^> Trusted Root Certification Authorities
echo.
choice /M "Continue uninstalling the certificate"
if errorlevel 2 exit /b 0

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($env:CERT_PATH)).Thumbprint"`) do set "CERT_THUMB=%%I"

if not defined CERT_THUMB (
    echo [ERROR] Failed to read certificate thumbprint.
    exit /b 1
)

call :cert_exists
if errorlevel 1 (
    echo [INFO] Certificate is not installed in Current User Root.
    exit /b 0
)

set /a REMOVE_TRIES=0
:remove_loop
set /a REMOVE_TRIES+=1
certutil -user -delstore Root "%CERT_THUMB%" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Certificate removal failed.
    exit /b 1
)

call :cert_exists
if errorlevel 1 goto removed_ok
if %REMOVE_TRIES% geq 8 (
    echo [ERROR] Certificate still exists in Current User Root after repeated removal attempts.
    exit /b 1
)
goto remove_loop

:removed_ok
call :verify_removed
if errorlevel 1 goto manual_fallback
echo [INFO] Certificate removed successfully.
exit /b 0

:cert_exists
certutil -user -store Root | findstr /I "%CERT_THUMB%" >nul
exit /b %errorlevel%

:verify_removed
powershell -NoProfile -ExecutionPolicy Bypass -Command "$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($env:CERT_PATH); $matches = @(Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }); if ($matches.Count -eq 0) { exit 0 } else { exit 1 }" >nul 2>nul
exit /b %errorlevel%

:manual_fallback
> "%GUIDE_PATH%" (
    echo AI_Mahjong Certificate Manual Removal Guide / AI_Mahjong 证书手动卸载说明
    echo ============================================================================
    echo.
    echo Automatic removal did not fully remove the certificate on this PC.
    echo 当前电脑未能完成证书自动卸载，请按下面步骤手动删除。
    echo.
    echo Thumbprint / 指纹:
    echo %CERT_THUMB%
    echo.
    echo Steps / 操作步骤:
    echo 1. In the opened Certificate Manager window, go to:
    echo 1. 在即将打开的证书管理器中，进入：
    echo    Trusted Root Certification Authorities ^> Certificates
    echo    受信任的根证书颁发机构 ^> 证书
    echo 2. Find the certificate whose Issuer or Subject is "mitmproxy".
    echo 2. 找到颁发者或主题为 "mitmproxy" 的证书。
    echo 3. If there are multiple matches, compare the thumbprint with the one above.
    echo 3. 如果有多个，请对照上面的指纹确认。
    echo 4. Right-click it and delete it.
    echo 4. 右键删除该证书。
)
start "" notepad "%GUIDE_PATH%" >nul 2>nul
start "" certmgr.msc >nul 2>nul
echo [WARN] Automatic removal could not fully delete the certificate.
echo [WARN] Manual guide has been opened.
exit /b 1
