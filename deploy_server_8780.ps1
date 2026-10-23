param(
    [string]$RepoPath = "C:\Users\Remote01\Desktop\Apki\THT_Inserter",
    [string]$Branch = "main",
    [int]$Port = 8780,
    [string]$BindHost = "0.0.0.0",
    [string]$PublicUrl = "http://192.168.1.10:8780",
    [string]$TaskName = "MSX THT Inserter 8780",
    [switch]$SkipGitPull,
    [switch]$InstallRequirements,
    [System.Management.Automation.PSCredential]$TaskCredential
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

    # Reload the deployed script, not the copy parsed before git pull.
    & $PSCommandPath -RepoPath $RepoPath -Branch $Branch -Port $Port -BindHost $BindHost `
        -PublicUrl $PublicUrl -TaskName $TaskName -SkipGitPull `
        -InstallRequirements:$InstallRequirements -TaskCredential $TaskCredential
    return
}

. (Join-Path $RepoPath 'platform_task_8780.ps1')

$python = Join-Path $RepoPath ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment..."
    Invoke-Checked "python" @("-m", "venv", ".venv")
}

if ($InstallRequirements) {
    Write-Host "Installing requirements..."
    Invoke-Checked $python @("-m", "pip", "install", "-r", "requirements.txt")
}

$runner = Join-Path $RepoPath 'run_platform_8780.ps1'
if (-not (Test-Path -LiteralPath $runner)) { throw "Runner script not found: $runner" }

# Register and verify permissions before taking the running app offline.
$platformTask = Register-PlatformTask -RepoPath $RepoPath -Port $Port -BindHost $BindHost `
    -PublicUrl $PublicUrl -TaskName $TaskName -TaskCredential $TaskCredential

# Prevent the recovery trigger from racing the deployment restart.
$platformTask.Enabled = $false
try {
    $platformTask.Stop(0)
    for ($i = 0; $i -lt 20 -and $platformTask.GetInstances(0).Count -gt 0; $i++) {
        Start-Sleep -Milliseconds 250
    }
    if ($platformTask.GetInstances(0).Count -gt 0) { throw 'Previous task instance did not stop.' }
    Stop-PortListener -LocalPort $Port
    Start-Sleep -Seconds 1
} finally {
    $platformTask.Enabled = $true
}
Write-Host "Starting MSX THT Inserter task on ${BindHost}:${Port}"
$platformTask.Run($null) | Out-Null

Wait-HealthCheck -LocalPort $Port

Write-Host "Network URL: $PublicUrl"
Write-Host "Lifecycle log: $(Join-Path $RepoPath "logs\inserter_platform_${Port}.lifecycle.log")"
