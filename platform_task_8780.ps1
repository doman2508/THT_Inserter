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

function Get-PlatformTaskUserKey {
    param([string]$UserId)
    if (-not $UserId) { return '' }
    if ($UserId -match '^S-1-') { return $UserId.ToUpperInvariant() }
    try {
        $account = New-Object Security.Principal.NTAccount -ArgumentList $UserId
        return $account.Translate([Security.Principal.SecurityIdentifier]).Value
    } catch {
        return $UserId.ToUpperInvariant()
    }
}

function Get-PlatformTaskSignature {
    param($Definition)
    $settings = $Definition.Settings
    $values = @((Get-PlatformTaskUserKey $Definition.Principal.UserId), $Definition.Principal.LogonType, $Definition.Principal.RunLevel)
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
        if ($trigger.Type -eq 9) { $values += @($trigger.Delay, (Get-PlatformTaskUserKey $trigger.UserId)) }
    }
    foreach ($action in $Definition.Actions) {
        $values += @($action.Type, $action.Path, $action.Arguments, $action.WorkingDirectory)
    }
    return ConvertTo-Json -InputObject $values -Compress
}

function Get-PlatformTaskAclRepair {
    param([Parameter(Mandatory)][string]$Sddl)

    $descriptor = [Security.AccessControl.RawSecurityDescriptor]::new($Sddl)
    if ($null -eq $descriptor.DiscretionaryAcl) {
        throw 'Task has a null DACL; automatic permission repair requires administrator review.'
    }
    $changed = $false
    # Restore only the standard scheduler trustees, only on this task. Never
    # change the scheduler folder, owner, principal, other ACEs or credentials.
    foreach ($sidText in @('S-1-5-32-544', 'S-1-5-18')) {
        $sid = [Security.Principal.SecurityIdentifier]::new($sidText)
        $allowed = 0
        foreach ($ace in $descriptor.DiscretionaryAcl) {
            if (([int]$ace.AceFlags -band [int][Security.AccessControl.AceFlags]::InheritOnly) -ne 0) { continue }
            # Fail closed for denials, including group/conditional ACEs. Do not
            # work around a deliberate security policy by inserting an allow.
            if ($ace -is [Security.AccessControl.QualifiedAce] -and
                $ace.AceQualifier -eq [Security.AccessControl.AceQualifier]::AccessDenied) {
                throw 'Task DACL contains a deny ACE; automatic repair requires administrator review.'
            }
            if ($ace -isnot [Security.AccessControl.CommonAce] -or $ace.IsCallback -or
                $ace.SecurityIdentifier -ne $sid -or
                $ace.AceQualifier -ne [Security.AccessControl.AceQualifier]::AccessAllowed) { continue }
            $mask = $ace.AccessMask
            # Map generic file rights before computing missing rights.
            if ($mask -band 0x10000000) { $mask = $mask -bor 0x1f01ff }
            if ($mask -band [int]::MinValue) { $mask = $mask -bor 0x120089 }
            if ($mask -band 0x40000000) { $mask = $mask -bor 0x120116 }
            if ($mask -band 0x20000000) { $mask = $mask -bor 0x1200a0 }
            $allowed = $allowed -bor $mask
        }
        $missing = 0x1f01ff -band (-bnot $allowed)
        if ($missing) {
            $newAce = [Security.AccessControl.CommonAce]::new(
                [Security.AccessControl.AceFlags]::None,
                [Security.AccessControl.AceQualifier]::AccessAllowed, $missing, $sid, $false, $null)
            $descriptor.DiscretionaryAcl.InsertAce(0, $newAce)
            $changed = $true
        }
    }
    return [pscustomobject]@{
        Changed = $changed
        Dacl = $descriptor.GetSddlForm([Security.AccessControl.AccessControlSections]::Access)
    }
}

function Repair-PlatformTaskPermissions {
    param($Task, [string]$TaskName, [string]$RepoPath, [int]$Port)

    # Names must identify one root task, not a folder or a wildcard.
    if (-not $TaskName -or $TaskName.IndexOfAny([char[]]'\/*?') -ge 0 -or
        $Task.Path -ne ('\' + $TaskName)) { throw 'Unexpected task path; ACL was not changed.' }
    $before = $Task.GetSecurityDescriptor(7)
    $repair = Get-PlatformTaskAclRepair -Sddl $before
    if (-not $repair.Changed) { return }
    $backupDir = Join-Path $RepoPath 'data\deploy-backups'
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $backupPath = Join-Path $backupDir ('task-{0}-acl-{1}.sddl' -f $Port, [guid]::NewGuid().ToString('N'))
    $before | Out-File -LiteralPath $backupPath -Encoding unicode
    Write-Host "Previous task ACL saved: $backupPath"
    if ($Task.GetSecurityDescriptor(7) -ne $before) {
        throw 'Task ACL changed concurrently; deployment stopped before restarting the app.'
    }
    # TASK_DONT_ADD_PRINCIPAL_ACE: preserve the task account's existing rights.
    $Task.SetSecurityDescriptor($repair.Dacl, 16)
    $after = $Task.GetSecurityDescriptor(7)
    if ((Get-PlatformTaskAclRepair -Sddl $after).Changed) {
        throw 'Task ACL verification failed; deployment stopped before restarting the app.'
    }
    Write-Host "Scheduler permissions repaired only for task '$TaskName'; stored credentials preserved."
}

function Start-PlatformTaskChecked {
    param($Task, [ValidateRange(0, 30)][int]$TimeoutSeconds = 15)

    if ($Task.Definition.Settings.MultipleInstances -ne 2) {
        throw 'Start preflight requires IgnoreNew to avoid duplicate application instances.'
    }
    if (-not $Task.Enabled -or -not $Task.Definition.Settings.AllowDemandStart) {
        throw 'Task is disabled or disallows on-demand start; existing app was not stopped.'
    }
    # Run() can succeed even when nothing starts. Check the task's live state,
    # not stale LastTaskResult. IgnoreNew can discard the returned instance;
    # GetInstances/EnginePID can also be hidden from a different logon context.
    # The caller must additionally check HTTP health. A running instance cannot
    # validate stored credentials for the next launch.
    $Task.Run($null) | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ($Task.State -eq 4) { return }
        if ([DateTime]::UtcNow -ge $deadline) { break }
        Start-Sleep -Milliseconds 250
    } while ($true)
    throw ("Task '{0}' accepted start but has no running process. LastTaskResult={1} (may be stale). " +
        'Check TaskScheduler/Operational as administrator, saved credentials and Log on as a batch job. ' +
        'The script does not change logon policies or fall back to session-dependent mode.') -f $Task.Name, $Task.LastTaskResult
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

    # An explicitly supplied credential must update stored credentials even if
    # the XML is unchanged (for example after changing the account password).
    if ($null -eq $TaskCredential -and $null -ne $existing -and (Get-PlatformTaskSignature $oldDefinition) -eq (Get-PlatformTaskSignature $definition)) {
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
    Repair-PlatformTaskPermissions -Task $registered -TaskName $TaskName -RepoPath $RepoPath -Port $Port
    if ($logonNumber -eq 3) {
        Write-Warning 'SESSION-DEPENDENT MODE: no 72h limit and recovery are enabled, but reboot without user logon requires one-time administrator setup with -TaskCredential.'
    } else {
        Write-Host "Background task configured for $userId; boot trigger: $bootTrigger."
    }
    return $registered
}
