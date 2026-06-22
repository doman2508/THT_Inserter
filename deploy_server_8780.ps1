param(
    [string]$RepoPath = "C:\Users\Remote01\Desktop\Apki\THT_Inserter",
    [string]$Branch = "main",
    [int]$Port = 8780,
    [string]$BindHost = "0.0.0.0",
    [string]$PublicUrl = "http://192.168.1.10:8780",
    [switch]$SkipGitPull,
    [switch]$InstallRequirements
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $FilePath $($ArgumentList -join ' ')"
    }
}

function Stop-PortListener {
    param([int]$LocalPort)

    $listeners = @()
    try {
        $listeners = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
    } catch {
        Write-Host "Get-NetTCPConnection is not available, using netstat fallback."
        $netstatLines = netstat -ano -p tcp | Select-String -Pattern ":$LocalPort\s+.*LISTENING"
        $listeners = foreach ($line in $netstatLines) {
            $parts = ($line.Line -split "\s+") | Where-Object { $_ }
            if ($parts.Count -ge 5) {
                [PSCustomObject]@{ OwningProcess = [int]$parts[-1] }
            }
        }
    }

    $processIds = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processIds) {
        if ($processId -gt 0) {
            Write-Host "Stopping process on port ${LocalPort}: PID ${processId}"
            Stop-Process -Id $processId -Force -ErrorAction Stop
        }
    }
}

function Wait-HealthCheck {
    param([int]$LocalPort)

    $uri = "http://127.0.0.1:${LocalPort}/api/health"
    for ($i = 1; $i -le 25; $i++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $uri -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Write-Host "Health check OK: $uri"
                return
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }

    throw "Application did not respond on $uri"
}

Set-Location $RepoPath

if (-not (Test-Path ".git")) {
    throw "This directory is not a Git repository: $RepoPath"
}

if (-not $SkipGitPull) {
    $dirty = git status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "git status failed"
    }
    if ($dirty) {
        throw "Working tree is not clean on server. Commit, stash or remove local changes first.`n$dirty"
    }

    Invoke-Checked "git" @("fetch", "origin")
    Invoke-Checked "git" @("checkout", $Branch)
    Invoke-Checked "git" @("pull", "--ff-only", "origin", $Branch)
}

$python = Join-Path $RepoPath ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment..."
    Invoke-Checked "python" @("-m", "venv", ".venv")
}

if ($InstallRequirements) {
    Write-Host "Installing requirements..."
    Invoke-Checked $python @("-m", "pip", "install", "-r", "requirements.txt")
}

Stop-PortListener -LocalPort $Port
Start-Sleep -Seconds 1

$logsDir = Join-Path $RepoPath "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
$stdoutLog = Join-Path $logsDir "inserter_platform_${Port}.out.log"
$stderrLog = Join-Path $logsDir "inserter_platform_${Port}.err.log"

$env:INSERTER_PLATFORM_HOST = $BindHost
$env:INSERTER_PLATFORM_PORT = [string]$Port
$env:INSERTER_PLATFORM_PUBLIC_URL = $PublicUrl

Write-Host "Starting MSX THT Inserter on ${BindHost}:${Port}"
$process = Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "inserter_platform.server") `
    -WorkingDirectory $RepoPath `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Write-Host "Started PID: $($process.Id)"
Start-Sleep -Seconds 1
if ($process.HasExited) {
    throw "Application process exited immediately. Check stderr log: $stderrLog"
}
Wait-HealthCheck -LocalPort $Port

Write-Host "Network URL: $PublicUrl"
Write-Host "Logs: $stdoutLog"
