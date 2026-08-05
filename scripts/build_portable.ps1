param(
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$buildEnvironment = Join-Path $projectRoot ".build-venv"
$buildPython = Join-Path $buildEnvironment "Scripts\python.exe"
$distributionRoot = Join-Path $projectRoot "dist"
$stagingRoot = Join-Path `
    ([System.IO.Path]::GetTempPath()) `
    ("AutoSearcher-build-" + [guid]::NewGuid().ToString("N"))
$portableRoot = Join-Path $stagingRoot "AutoSearcher"
$archivePath = Join-Path $distributionRoot "AutoSearcher-portable-win-x64.zip"
New-Item -ItemType Directory -Force -Path $distributionRoot | Out-Null

if (-not (Test-Path -LiteralPath $buildPython)) {
    & $PythonCommand -m venv $buildEnvironment
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create build environment."
    }
}

& $buildPython -m pip install `
    --disable-pip-version-check `
    "setuptools>=68"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install the build backend."
}
& $buildPython -m pip install `
    --disable-pip-version-check `
    --no-build-isolation `
    -e "${projectRoot}[build]"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install build dependencies."
}

& $buildPython -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $stagingRoot `
    --workpath (Join-Path $projectRoot "build") `
    (Join-Path $projectRoot "packaging\AutoSearcher.spec")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$configDirectory = Join-Path $portableRoot "config"
$dataDirectory = Join-Path $portableRoot "data"
New-Item -ItemType Directory -Force -Path $configDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $dataDirectory | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "config\config.yaml") `
    -Destination $configDirectory -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "data\fallback_topics.txt") `
    -Destination $dataDirectory -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "packaging\run.cmd") `
    -Destination $portableRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "packaging\check.cmd") `
    -Destination $portableRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") `
    -Destination $portableRoot -Force

& (Join-Path $portableRoot "AutoSearcher.exe") `
    --config (Join-Path $configDirectory "config.yaml") check
if ($LASTEXITCODE -ne 0) {
    throw "Packaged runtime validation failed."
}

$archiveCreated = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    if (Test-Path -LiteralPath $archivePath) {
        Remove-Item -LiteralPath $archivePath -Force
    }
    try {
        Compress-Archive -Path (Join-Path $portableRoot "*") `
            -DestinationPath $archivePath -CompressionLevel Optimal
        $archiveCreated = $true
        break
    }
    catch {
        if ($attempt -eq 3) {
            throw
        }
        Start-Sleep -Seconds 2
    }
}
if (-not $archiveCreated) {
    throw "Failed to create portable archive."
}

$sizeMegabytes = (Get-Item -LiteralPath $archivePath).Length / 1MB
Write-Host "Portable package: $archivePath"
Write-Host ("Archive size: {0:N2} MB" -f $sizeMegabytes)

try {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction Stop
}
catch {
    Write-Warning "Temporary build directory is still in use: $stagingRoot"
}
