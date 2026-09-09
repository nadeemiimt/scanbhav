# Build Stock Adda distributable for Windows (.exe folder + zip).
# Run in PowerShell on Windows:
#   .\scripts\build-release.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Version = if ($env:STOCK_ADDA_VERSION) { $env:STOCK_ADDA_VERSION } else { "0.6.0" }
$ReleaseDir = Join-Path $Root "dist\release"
$AppName = "StockAdda"

Write-Host "[release] Stock Adda v$Version"

$venvActivate = Join-Path $Root ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) { . $venvActivate }

Write-Host "[release] 1/5 — frontend production build"
$frontend = Join-Path $Root "frontend"
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Push-Location $frontend; npm install; Pop-Location
}
Push-Location $frontend; npm run build; Pop-Location

Write-Host "[release] 2/5 — bundle seed data"
python (Join-Path $Root "packaging\prepare_bundle_data.py")

Write-Host "[release] 3/5 — PyInstaller"
pip install -q -r (Join-Path $Root "requirements-packaging.txt")
pyinstaller (Join-Path $Root "packaging\stock_adda.spec") --clean --noconfirm `
    --distpath (Join-Path $Root "dist") `
    --workpath (Join-Path $Root "build\pyinstaller")

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$BundleSrc = Join-Path $Root "dist\StockAdda"
$BundleDest = Join-Path $ReleaseDir "StockAdda"
if (Test-Path $BundleDest) { Remove-Item -Recurse -Force $BundleDest }
Copy-Item -Recurse $BundleSrc $BundleDest

$ZipPath = Join-Path $ReleaseDir "StockAdda-Windows-v$Version.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path $BundleDest -DestinationPath $ZipPath

Write-Host "[release] 4/5 — done"
Write-Host "  Folder: $BundleDest"
Write-Host "  EXE:    $(Join-Path $BundleDest 'StockAdda.exe')"
Write-Host "  ZIP:    $ZipPath"
Write-Host "[release] First launch stores data in %LOCALAPPDATA%\StockAdda"
