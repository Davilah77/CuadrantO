$ErrorActionPreference = "Stop"
$ProjectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location $ProjectDirectory
$Version = (python -c "from core.version import __version__; print(__version__)").Trim()
$ReleaseDirectory = Join-Path $ProjectDirectory "release\Cuadrante-portable-$Version"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Cuadrante app.py

New-Item -ItemType Directory -Force -Path $ReleaseDirectory | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectDirectory "dist\Cuadrante.exe") -Destination $ReleaseDirectory -Force
Copy-Item -LiteralPath (Join-Path $ProjectDirectory "LEEME-PORTABLE.txt") -Destination $ReleaseDirectory -Force

$ZipPath = Join-Path $ProjectDirectory "release\Cuadrante-portable-$Version-windows-x64.zip"
Compress-Archive -Path (Join-Path $ReleaseDirectory "*") -DestinationPath $ZipPath -Force
Write-Output $ZipPath
