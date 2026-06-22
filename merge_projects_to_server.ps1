param(
    [string]$SshHost = "api-vendo-prod",
    [string]$RepoPath = "C:\Users\Remote01\Desktop\Apki\THT_Inserter",
    [string]$LocalDataPath = "data",
    [switch]$Apply,
    [switch]$AllowNameDuplicates
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

$localDb = Join-Path $LocalDataPath "inserter_platform.db"
$localUploads = Join-Path $LocalDataPath "uploads"
if (-not (Test-Path $localDb)) {
    throw "Local database not found: $localDb"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$repoPathRemote = $RepoPath.Replace("\", "/")
$incomingRemote = "$repoPathRemote/_incoming_projects/$stamp"

Write-Host "Creating remote incoming directory: $incomingRemote"
Invoke-Checked "ssh" @(
    $SshHost,
    "powershell -NoProfile -Command `"New-Item -ItemType Directory -Force -Path '$incomingRemote' | Out-Null`""
)

Write-Host "Uploading local database snapshot..."
Invoke-Checked "scp" @($localDb, "${SshHost}:$incomingRemote/inserter_platform.db")

if (Test-Path $localUploads) {
    Write-Host "Uploading local uploads..."
    Invoke-Checked "scp" @("-r", $localUploads, "${SshHost}:$incomingRemote/")
} else {
    Write-Host "No local uploads directory found, continuing without uploads."
}

$python = "$repoPathRemote/.venv/Scripts/python.exe"
$script = "$repoPathRemote/scripts/merge_project_data.py"
$destDb = "$repoPathRemote/data/inserter_platform.db"
$destUploads = "$repoPathRemote/data/uploads"
$sourceDb = "$incomingRemote/inserter_platform.db"
$sourceUploads = "$incomingRemote/uploads"

$mergeArgs = @(
    "--source", $sourceDb,
    "--dest", $destDb,
    "--source-uploads", $sourceUploads,
    "--dest-uploads", $destUploads
)
if ($Apply) {
    $mergeArgs += "--apply"
}
if ($AllowNameDuplicates) {
    $mergeArgs += "--allow-name-duplicates"
}

$quotedArgs = ($mergeArgs | ForEach-Object { "'$_'" }) -join " "
$remoteCommand = "cd '$repoPathRemote'; & '$python' '$script' $quotedArgs"

$mode = "PLAN"
if ($Apply) {
    $mode = "APPLY"
}
Write-Host "Running remote merge $mode..."
Invoke-Checked "ssh" @(
    $SshHost,
    "powershell -NoProfile -ExecutionPolicy Bypass -Command `"$remoteCommand`""
)
