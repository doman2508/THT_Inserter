param(
    [string]$RepoPath = "C:\Users\Remote01\Desktop\Apki\THT_Inserter",
    [int]$Port = 8780,
    [string]$BindHost = "0.0.0.0",
    [string]$PublicUrl = "http://192.168.1.10:8780"
)

$ErrorActionPreference = "Stop"

Set-Location $RepoPath

$env:INSERTER_PLATFORM_HOST = $BindHost
$env:INSERTER_PLATFORM_PORT = [string]$Port
$env:INSERTER_PLATFORM_PUBLIC_URL = $PublicUrl

$python = Join-Path $RepoPath ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$logsDir = Join-Path $RepoPath "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
$logPath = Join-Path $logsDir "inserter_platform_${Port}.task.log"

"$(Get-Date -Format s) Starting MSX THT Inserter on ${BindHost}:${Port}" | Out-File -FilePath $logPath -Append -Encoding utf8
& $python -m inserter_platform.server *>> $logPath
