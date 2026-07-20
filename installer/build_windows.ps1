# Build CombinePro.exe and a Windows setup installer.
#
#   powershell -ExecutionPolicy Bypass -File installer\build_windows.ps1
#
# Requires: Python 3.10-3.14, Node.js (to vendor the sidecar), and Inno Setup 6
# (https://jrsoftware.org/isdl.php) for the installer step.
#
# NOTE: this must run ON Windows. PyInstaller does not cross-compile, so a
# Windows .exe cannot be produced from macOS or Linux.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$AppName = "CombinePro"
$Version = "1.0.5"
$Python  = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$Dist    = Join-Path $Root "installer\dist"
$Work    = Join-Path $Root "installer\work"

Write-Host "==> Checking toolchain" -ForegroundColor Cyan
& $Python --version
try { & $Python -c "import PyInstaller" 2>$null }
catch { Write-Host "Installing PyInstaller"; & $Python -m pip install -q pyinstaller }

Write-Host "==> Installing sidecar dependencies (bundled into the app)" -ForegroundColor Cyan
if (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location (Join-Path $Root "sidecar")
    npm install --omit=dev --silent
    Pop-Location
} else {
    Write-Warning "npm not found - the sidecar ships without node_modules; Delta Memory will be disabled."
}

Write-Host "==> Generating icons" -ForegroundColor Cyan
$env:QT_QPA_PLATFORM = "offscreen"
& $Python (Join-Path $Root "installer\make_icons.py")
Remove-Item Env:\QT_QPA_PLATFORM

Write-Host "==> Building executable" -ForegroundColor Cyan
if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
& $Python -m PyInstaller (Join-Path $Root "installer\$AppName.spec") `
    --noconfirm --distpath $Dist --workpath $Work
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Exe = Join-Path $Dist "$AppName\$AppName.exe"
if (-not (Test-Path $Exe)) { throw "Build failed: $Exe missing" }

Write-Host "==> Self-testing the bundle" -ForegroundColor Cyan
& $Exe --selftest
if ($LASTEXITCODE -ne 0) { throw "Bundle self-test FAILED - not packaging a broken app." }

Write-Host "==> Building installer" -ForegroundColor Cyan
$Iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($Iscc) {
    Push-Location (Join-Path $Root "installer")
    & $Iscc "CombinePro.iss"
    Pop-Location
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    $Setup = Join-Path $Dist "$AppName-$Version-Windows-Setup.exe"
    Write-Host ""
    Write-Host "OK  Installer: $Setup" -ForegroundColor Green
    Write-Host "Install: double-click the setup .exe."
} else {
    Write-Warning "Inno Setup 6 not found - skipping installer."
    Write-Host "OK  Portable build: $Dist\$AppName\" -ForegroundColor Green
    Write-Host "Install Inno Setup from https://jrsoftware.org/isdl.php to produce a setup .exe."
}

Write-Host ""
Write-Host "Note: unsigned builds trigger SmartScreen ('More info' > 'Run anyway')."
Write-Host "      Sign with signtool.exe and a code-signing certificate to avoid it."
