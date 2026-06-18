param(
    [string]$SshHost = "api-vendo-prod",
    [string]$RepoPath = "C:\Users\Remote01\Desktop\Apki\THT_Inserter",
    [switch]$InstallRequirements
)

$ErrorActionPreference = "Stop"

$remoteCommand = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$RepoPath\deploy_server_8780.ps1`""
if ($InstallRequirements) {
    $remoteCommand = "$remoteCommand -InstallRequirements"
}

ssh $SshHost $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Remote deploy failed"
}
