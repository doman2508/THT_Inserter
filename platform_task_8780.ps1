function New-PlatformTaskXml {
    param(
        [string]$RepoPath,
        [int]$Port,
        [string]$BindHost,
        [string]$PublicUrl,
        [string]$UserId,
        [ValidateSet('InteractiveToken', 'Password', 'S4U')]
        [string]$LogonType,
        [string]$StartBoundary,
        [bool]$BootTrigger = $false
    )

    $runner = Join-Path $RepoPath 'run_platform_8780.ps1'
    $arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -RepoPath "{1}" -Port {2} -BindHost "{3}" -PublicUrl "{4}"' -f $runner, $RepoPath, $Port, $BindHost, $PublicUrl
    $xmlArguments = [Security.SecurityElement]::Escape($arguments)
    $xmlRepo = [Security.SecurityElement]::Escape($RepoPath)
    $xmlUser = [Security.SecurityElement]::Escape($UserId)
    $xmlBoundary = [Security.SecurityElement]::Escape($StartBoundary)
    $bootXml = ''
    if ($BootTrigger) {
        $bootXml = '<BootTrigger id="InserterBoot"><Enabled>true</Enabled><ExecutionTimeLimit>PT0S</ExecutionTimeLimit><Delay>PT30S</Delay></BootTrigger>'
    }
    return @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>MSX THT Inserter: continuous operation and automatic recovery.</Description></RegistrationInfo>
  <Triggers>
    <TimeTrigger id="InserterRetry">
      <Repetition><Interval>PT1M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>$xmlBoundary</StartBoundary><Enabled>true</Enabled><ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    </TimeTrigger>
    <LogonTrigger id="InserterLogon"><Enabled>true</Enabled><ExecutionTimeLimit>PT0S</ExecutionTimeLimit><UserId>$xmlUser</UserId></LogonTrigger>
    $bootXml
  </Triggers>
  <Principals><Principal id="Inserter"><UserId>$xmlUser</UserId><LogonType>$LogonType</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled><Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle><WakeToRun>false</WakeToRun><ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Inserter"><Exec><Command>powershell.exe</Command><Arguments>$xmlArguments</Arguments><WorkingDirectory>$xmlRepo</WorkingDirectory></Exec></Actions>
</Task>
"@
}

function Get-PlatformTaskSignature {
    param($Definition)
    $settings = $Definition.Settings
    $values = @($Definition.Principal.UserId, $Definition.Principal.LogonType, $Definition.Principal.RunLevel)
    foreach ($property in @('MultipleInstances', 'DisallowStartIfOnBatteries', 'StopIfGoingOnBatteries',
        'AllowHardTerminate', 'StartWhenAvailable', 'RunOnlyIfNetworkAvailable', 'AllowDemandStart',
        'Hidden', 'RunOnlyIfIdle', 'WakeToRun', 'ExecutionTimeLimit', 'RestartInterval', 'RestartCount')) {
        $values += $settings.$property
    }
    $values += @($settings.IdleSettings.StopOnIdleEnd, $settings.IdleSettings.RestartOnIdle)
    foreach ($trigger in $Definition.Triggers) {
        $values += @($trigger.Id, $trigger.Type, $trigger.Enabled, $trigger.StartBoundary, $trigger.EndBoundary,
            $trigger.ExecutionTimeLimit, $trigger.Repetition.Interval, $trigger.Repetition.Duration, $trigger.Repetition.StopAtDurationEnd)
        if ($trigger.Type -eq 8) { $values += $trigger.Delay }
        if ($trigger.Type -eq 9) { $values += @($trigger.Delay, $trigger.UserId) }
    }
    foreach ($action in $Definition.Actions) {
        $values += @($action.Type, $action.Path, $action.Arguments, $action.WorkingDirectory)
    }
    return ConvertTo-Json -InputObject $values -Compress
}

function Register-PlatformTask {
    param(
        [string]$RepoPath,
        [int]$Port,
        [string]$BindHost,
        [string]$PublicUrl,
        [string]$TaskName,
        [System.Management.Automation.PSCredential]$TaskCredential
    )

    $service = New-Object -ComObject 'Schedule.Service'
    $service.Connect()
    $folder = $service.GetFolder('\')
    $existing = $null
    try { $existing = $folder.GetTask($TaskName) } catch {
        if ($_.Exception.GetBaseException().HResult -ne -2147024894) { throw }
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $userId = $identity.Name
    $logonType = 'InteractiveToken'
    $logonNumber = 3
    $startBoundary = (Get-Date).AddMinutes(1).ToString('yyyy-MM-ddTHH:mm:ss')
    $bootTrigger = $isAdmin
    if ($null -ne $existing) {
        $oldDefinition = $existing.Definition
        $userId = $oldDefinition.Principal.UserId
        $logonNumber = $oldDefinition.Principal.LogonType
        switch ($logonNumber) {
            1 { $logonType = 'Password' }
            2 { $logonType = 'S4U' }
            3 { $logonType = 'InteractiveToken' }
            default { throw "Unsupported task logon type $logonNumber; existing task was not changed." }
        }
        foreach ($trigger in $oldDefinition.Triggers) {
            if ($trigger.Id -eq 'InserterRetry') { $startBoundary = $trigger.StartBoundary }
            if ($trigger.Type -eq 8) { $bootTrigger = $true }
        }
    }
    if ($null -ne $TaskCredential) {
        if (-not $isAdmin) { throw 'Run this one-time background task setup from an administrator PowerShell.' }
        $userId = $TaskCredential.UserName
        $logonType = 'Password'
        $logonNumber = 1
    }
    $definition = $service.NewTask(0)
    $definition.XmlText = New-PlatformTaskXml -RepoPath $RepoPath -Port $Port -BindHost $BindHost `
        -PublicUrl $PublicUrl -UserId $userId -LogonType $logonType -StartBoundary $startBoundary -BootTrigger $bootTrigger

    if ($null -ne $existing -and (Get-PlatformTaskSignature $oldDefinition) -eq (Get-PlatformTaskSignature $definition)) {
        Write-Host 'Existing task configuration is current; stored credentials are preserved.'
        $registered = $existing
    } else {
        if ($logonNumber -eq 1 -and $null -eq $TaskCredential) {
            throw 'Updating this background task requires -TaskCredential from an administrator PowerShell. The running task was not stopped.'
        }
        if ($null -ne $existing) {
            $backupDir = Join-Path $RepoPath 'data\deploy-backups'
            New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
            $backupPath = Join-Path $backupDir ('task-{0}-{1}.xml' -f $Port, [guid]::NewGuid().ToString('N'))
            $existing.Xml | Out-File -LiteralPath $backupPath -Encoding unicode
            Write-Host "Previous task definition saved: $backupPath"
        }
        $taskPassword = $null
        try {
            if ($null -ne $TaskCredential) { $taskPassword = $TaskCredential.GetNetworkCredential().Password }
            $registered = $folder.RegisterTaskDefinition($TaskName, $definition, 6, $userId, $taskPassword, $logonNumber)
        } finally { $taskPassword = $null }
    }
    if ($logonNumber -eq 3) {
        Write-Warning 'SESSION-DEPENDENT MODE: no 72h limit and recovery are enabled, but reboot without user logon requires one-time administrator setup with -TaskCredential.'
    } else {
        Write-Host "Background task configured for $userId; boot trigger: $bootTrigger."
    }
    return $registered
}
