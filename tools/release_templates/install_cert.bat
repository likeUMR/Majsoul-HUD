@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "CERT_PATH=%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.cer"

if not exist "%CERT_PATH%" (
    echo [ERROR] mitmproxy certificate was not found:
    echo   %CERT_PATH%
    echo.
    echo Please run start_all.bat once first so mitmproxy can generate its CA certificate.
    exit /b 1
)

echo ==================================================
echo             Install mitmproxy Certificate
echo ==================================================
echo This will import the mitmproxy CA certificate into:
echo   Current User ^> Trusted Root Certification Authorities
echo.
echo This is required so the Majsoul HTTPS/WSS traffic can be decrypted locally.
echo.
choice /M "Continue installing the certificate"
if errorlevel 2 exit /b 0

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($env:CERT_PATH);" ^
  "$store = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root','CurrentUser');" ^
  "$store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite);" ^
  "$exists = @($store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }).Count -gt 0;" ^
  "if ($exists) { Write-Host '[INFO] Certificate is already installed.'; $store.Close(); exit 0 }" ^
  "$store.Add($cert);" ^
  "$store.Close();" ^
  "Write-Host '[INFO] Certificate installed successfully.'"

if errorlevel 1 (
    echo [ERROR] Certificate installation failed.
    exit /b 1
)

echo [INFO] Done. Reopen the browser after installation.
exit /b 0
