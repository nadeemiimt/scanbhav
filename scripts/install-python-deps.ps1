# Install Scan Bhav Python deps in a resolver-safe order (Windows).
# FYERS is installed with --no-deps because it pins requests==2.31.0 / aiohttp==3.9.3
# while growwapi needs newer versions.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

Write-Host "[deps] core"
& $Python -m pip install -U pip setuptools wheel
& $Python -m pip install -r (Join-Path $Root "requirements.txt")

Write-Host "[deps] kiteconnect + growwapi"
& $Python -m pip install "kiteconnect>=5.0" "growwapi>=1.5"

Write-Host "[deps] fyers-apiv3 (--no-deps)"
& $Python -m pip install "fyers-apiv3>=3.1.14" --no-deps
try {
    & $Python -m pip install "websocket-client>=1.6"
} catch {
    Write-Host "[deps] websocket-client optional install skipped"
}

if ($env:SCAN_BHAV_INSTALL_OPTIONAL -eq "1") {
    Write-Host "[deps] optional"
    try {
        & $Python -m pip install -r (Join-Path $Root "requirements-optional.txt")
    } catch {
        Write-Host "[deps] optional skipped"
    }
}

if ($env:SCAN_BHAV_INSTALL_PACKAGING -eq "1") {
    Write-Host "[deps] packaging"
    & $Python -m pip install -r (Join-Path $Root "requirements-packaging.txt")
}

Write-Host "[deps] done"
