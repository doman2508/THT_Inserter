$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
. (Join-Path $repo 'platform_task_8780.ps1')

function Assert-Equal($Actual, $Expected, $Label) {
    if ($Actual -ne $Expected) { throw "${Label}: expected '$Expected', got '$Actual'" }
}

foreach ($name in @('deploy_server_8780.ps1', 'deploy_from_local_8780.ps1', 'run_platform_8780.ps1', 'platform_task_8780.ps1', 'diagnose_platform_task_8780.ps1', 'grant_platform_batch_logon_8780.ps1')) {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $repo $name), [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count) { throw ($errors | Out-String) }
}

$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$taskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
foreach ($mode in @('InteractiveToken', 'Password', 'S4U')) {
    foreach ($boot in @($false, $true)) {
        $xml = New-PlatformTaskXml -RepoPath 'C:\Task test & spaces\Inserter' -Port 18780 -BindHost '127.0.0.1' `
            -PublicUrl 'http://127.0.0.1:18780/?a=1&b=2' -UserId $taskUser -LogonType $mode `
            -StartBoundary '2026-10-23T10:00:00' -BootTrigger $boot
        $definition = $service.NewTask(0)
        $definition.XmlText = $xml
        Assert-Equal $definition.Settings.ExecutionTimeLimit 'PT0S' 'No execution limit'
        Assert-Equal $definition.Settings.RestartInterval 'PT1M' 'Failure restart interval'
        Assert-Equal $definition.Settings.RestartCount 999 'Failure retries'
        Assert-Equal $definition.Settings.MultipleInstances 2 'Ignore duplicate starts'
        Assert-Equal $definition.Settings.StartWhenAvailable $true 'Catch up missed starts'
        Assert-Equal $definition.Settings.StopIfGoingOnBatteries $false 'No UPS shutdown'
        Assert-Equal $definition.Principal.RunLevel 0 'Least privilege'
        Assert-Equal $definition.Triggers.Count (2 + [int]$boot) 'Trigger count'
        $retry = $definition.Triggers.Item(1)
        Assert-Equal $retry.Repetition.Interval 'PT1M' 'Periodic recovery'
        Assert-Equal ([string]$retry.Repetition.Duration) '' 'Recovery never expires'
        Assert-Equal $retry.ExecutionTimeLimit 'PT0S' 'No trigger execution limit'
        Assert-Equal $definition.Actions.Item(1).WorkingDirectory 'C:\Task test & spaces\Inserter' 'Escaped working directory'
        if (-not $definition.Actions.Item(1).Arguments.Contains('"C:\Task test & spaces\Inserter\run_platform_8780.ps1"')) { throw 'Runner path was not quoted' }
        if ($boot) { Assert-Equal $definition.Triggers.Item(3).Type 8 'Boot trigger' }
        $roundtrip = $service.NewTask(0)
        $roundtrip.XmlText = $definition.XmlText
        Assert-Equal (Get-PlatformTaskSignature $definition) (Get-PlatformTaskSignature $roundtrip) 'Idempotent task configuration'
        $roundtrip.Triggers.Item(2).UserId = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        Assert-Equal (Get-PlatformTaskSignature $definition) (Get-PlatformTaskSignature $roundtrip) 'Account name and SID are equivalent'
        $roundtrip.Settings.ExecutionTimeLimit = 'PT72H'
        if ((Get-PlatformTaskSignature $definition) -eq (Get-PlatformTaskSignature $roundtrip)) { throw 'Regression to 72h was not detected' }
    }
}
Write-Host 'Task configuration OK: 6 variants, no time limit, retry, boot/logon, quoting and idempotence. No tasks registered.'
