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
$logPath = Join-Path $logsDir "inserter_platform_${Port}.lifecycle.log"
$runId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss-fff'), $PID
$stdoutPath = Join-Path $logsDir "inserter_platform_${Port}.${runId}.stdout.log"
$stderrPath = Join-Path $logsDir "inserter_platform_${Port}.${runId}.stderr.log"
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONIOENCODING = 'utf-8'

try {
    "$(Get-Date -Format s) Starting on ${BindHost}:${Port}; stdout=$stdoutPath; stderr=$stderrPath" | Out-File -LiteralPath $logPath -Append -Encoding utf8
    # Separate stderr avoids PowerShell 5.1 NativeCommandError terminating the runner.
    $serverProcess = Start-Process -FilePath $python -ArgumentList @('-u', '-m', 'inserter_platform.server') `
        -WorkingDirectory $RepoPath -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    # Cache the process handle before waiting (PowerShell 5.1 otherwise loses ExitCode).
    $null = $serverProcess.Handle
    "$(Get-Date -Format s) Python PID=$($serverProcess.Id)" | Out-File -LiteralPath $logPath -Append -Encoding utf8
    $serverProcess.WaitForExit()
    $serverExitCode = $serverProcess.ExitCode
    "$(Get-Date -Format s) Python exited: $serverExitCode; scheduling recovery." | Out-File -LiteralPath $logPath -Append -Encoding utf8
} catch {
    "$(Get-Date -Format s) Runner failed: $($_.Exception.Message)" | Out-File -LiteralPath $logPath -Append -Encoding utf8
}

# This is a persistent server: even an unexpected exit(0) must trigger recovery.
exit 1
