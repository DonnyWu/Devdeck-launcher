# Build DevDeck.exe with PyInstaller.
# Run from the DevDeck folder:  .\build.ps1
# Output: dist\DevDeck\DevDeck.exe  (onedir = faster startup)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Use the project venv if present, else system python.
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

& $py -m PyInstaller --noconfirm --clean --windowed --name DevDeck `
    --collect-submodules PySide6 `
    run.py

Write-Host ""
Write-Host "Built: $(Join-Path $PSScriptRoot 'dist\DevDeck\DevDeck.exe')"
Write-Host "(For a single portable file, re-run with --onefile instead of onedir.)"
