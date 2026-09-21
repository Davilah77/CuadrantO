$ErrorActionPreference = "Stop"
$ProjectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$ReleaseDirectory = Join-Path $ProjectDirectory "release\Cuadrante-portable-0.1.0"

Set-Location $ProjectDirectory
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Cuadrante app.py

New-Item -ItemType Directory -Force -Path $ReleaseDirectory | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectDirectory "dist\Cuadrante.exe") -Destination $ReleaseDirectory -Force
Copy-Item -LiteralPath (Join-Path $ProjectDirectory "LEEME-PORTABLE.txt") -Destination $ReleaseDirectory -Force

$ZipPath = Join-Path $ProjectDirectory "release\Cuadrante-portable-0.1.0-windows-x64.zip"
Compress-Archive -Path (Join-Path $ReleaseDirectory "*") -DestinationPath $ZipPath -Force
Write-Output $ZipPath

