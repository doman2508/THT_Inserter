param([int]$TimeoutSeconds = 90)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
. (Join-Path $repo 'platform_task_8780.ps1')
$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$folder = $service.GetFolder('\')
$name = 'MSX THT Inserter recovery test ' + [guid]::NewGuid().ToString('N')
$markerPath = Join-Path ([IO.Path]::GetTempPath()) ('inserter-recovery-' + [guid]::NewGuid().ToString('N') + '.log')
$definition = $service.NewTask(0)
$definition.XmlText = New-PlatformTaskXml -RepoPath $repo -Port 18780 -BindHost '127.0.0.1' `
    -PublicUrl 'http://127.0.0.1:18780' -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType InteractiveToken -StartBoundary ((Get-Date).AddMinutes(1).ToString('yyyy-MM-ddTHH:mm:ss'))
# Exercise the complete recovery policy, including its periodic safety net.
# Only the test command runs; the real app is never launched or stopped here.
$definition.Settings.RestartCount = 1
$markerArgument = $markerPath.Replace("'", "''")
$definition.Actions.Item(1).Arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -Command "(Get-Date -Format o) | Add-Content -LiteralPath ''{0}''; exit 7"' -f $markerArgument
$registered = $null
try {
    $registered = $folder.RegisterTaskDefinition($name, $definition, 2, $definition.Principal.UserId, $null, 3)
    $started = Get-Date
    $registered.Run($null) | Out-Null
    $restarted = $false
    Write-Host 'Temporary test task intentionally exits with code 7. Waiting for automatic retry (~1 minute).'
    do {
        Start-Sleep -Seconds 2
        $registered = $folder.GetTask($name)
        # LastRunTime can remain unchanged for RestartOnFailure of the same instance.
        if (Test-Path -LiteralPath $markerPath) {
            $runs = @(Get-Content -LiteralPath $markerPath)
            if ($runs.Count -ge 2) {
                $restarted = $true
                Write-Host ('Automatic restart verified: ' + ($runs -join ', '))
            }
        }
    } until ($restarted -or (Get-Date) -gt $started.AddSeconds($TimeoutSeconds))
    if (-not $restarted) { throw "Automatic restart was not observed. Last result: $($registered.LastTaskResult)" }
} finally {
    if ($null -ne $registered) {
        $registered.Enabled = $false
        $registered.Stop(0)
        $folder.DeleteTask($name, 0)
        Write-Host 'Temporary recovery test task removed; the application was not stopped.'
    }
    if (Test-Path -LiteralPath $markerPath) { Remove-Item -LiteralPath $markerPath }
}
