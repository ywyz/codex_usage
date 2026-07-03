$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VersionTag = if ($env:VERSION_TAG) { $env:VERSION_TAG } else { Get-Date -Format "yyyyMMdd-HHmmss" }
$ArtifactDir = Join-Path $RootDir "release/windows"
$DistDir = Join-Path $RootDir "dist"
$BuildVenvDir = Join-Path $RootDir ".venv-build"
$ArchiveBaseName = "codex-usage-widget-windows-x86_64-$VersionTag"
$ArchiveDir = Join-Path $ArtifactDir $ArchiveBaseName

Set-Location $RootDir

New-Item -ItemType Directory -Path $ArtifactDir -Force | Out-Null
python -m venv $BuildVenvDir
& (Join-Path $BuildVenvDir "Scripts/python.exe") -m pip install --upgrade pip
& (Join-Path $BuildVenvDir "Scripts/python.exe") -m pip install -r packaging/requirements-build.txt
& (Join-Path $BuildVenvDir "Scripts/python.exe") -m PyInstaller --clean --noconfirm packaging/codex_usage_widget.spec

if (Test-Path $ArchiveDir) {
    Remove-Item $ArchiveDir -Recurse -Force
}
New-Item -ItemType Directory -Path $ArchiveDir -Force | Out-Null
Copy-Item (Join-Path $DistDir "codex-usage-widget.exe") $ArchiveDir
Copy-Item (Join-Path $RootDir "README.md") $ArchiveDir

$ZipPath = Join-Path $ArtifactDir "$ArchiveBaseName.zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path (Join-Path $ArchiveDir "*") -DestinationPath $ZipPath

Write-Output "Windows package created: $ZipPath"
