$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
. (Join-Path $repo 'platform_task_8780.ps1')

function Assert-Equal($Actual, $Expected, $Label) {
    if ($Actual -ne $Expected) { throw "${Label}: expected '$Expected', got '$Actual'" }
}
function Assert-Throws([scriptblock]$Action, [string]$Pattern) {
    $caught = $false
    try { & $Action } catch {
        $caught = $true
        if ($_.Exception.Message -notlike $Pattern) { throw }
    }
    if (-not $caught) { throw "Expected failure matching: $Pattern" }
}
function Get-AceBytes($Ace) {
    $bytes = New-Object byte[] $Ace.BinaryLength
    $Ace.GetBinaryForm($bytes, 0)
    return [Convert]::ToBase64String($bytes)
}
function New-FakeTask([string]$Sddl) {
    $task = [pscustomobject]@{
        Name = 'MSX THT Inserter 8780'; Path = '\MSX THT Inserter 8780'
        Sddl = $Sddl; Enabled = $true; SetCount = 0; RunCount = 0; ReadCount = 0
        IgnoreWrite = $false; ConcurrentChange = $false; LastTaskResult = 267014
        InstanceState = 4; InstancePid = 123; RefreshFailure = $false
        Definition = [pscustomobject]@{Settings = [pscustomobject]@{MultipleInstances = 2; AllowDemandStart = $true}}
    }
    $task | Add-Member ScriptMethod GetSecurityDescriptor {
        param($Sections)
        Assert-Equal $Sections 7 'Read owner/group/DACL only'
        $this.ReadCount++
        if ($this.ConcurrentChange -and $this.ReadCount -gt 1) { return 'O:SYG:SYD:(A;;FA;;;SY)' }
        return $this.Sddl
    }
    $task | Add-Member ScriptMethod SetSecurityDescriptor {
        param($Dacl, $Flags)
        Assert-Equal $Flags 16 'Do not add task principal ACE'
        if (-not $Dacl.StartsWith('D:')) { throw 'Setter must receive DACL only' }
        $this.SetCount++
        if (-not $this.IgnoreWrite) {
            $old = [Security.AccessControl.RawSecurityDescriptor]::new($this.Sddl)
            $updated = [Security.AccessControl.RawSecurityDescriptor]::new($Dacl)
            $old.DiscretionaryAcl = $updated.DiscretionaryAcl
            $this.Sddl = $old.GetSddlForm([Security.AccessControl.AccessControlSections]::All)
        }
    }
    $task | Add-Member ScriptMethod Run {
        param($Parameters)
        $this.RunCount++
        $instance = [pscustomobject]@{State=$this.InstanceState; EnginePID=$this.InstancePid; Fail=$this.RefreshFailure}
        $instance | Add-Member ScriptMethod Refresh { if ($this.Fail) { throw 'Instance no longer exists' } }
        return $instance
    }
    return $task
}

$userSid = 'S-1-5-21-111-222-333-1019'
$broken = "O:${userSid}G:BAD:(A;;FR;;;${userSid})(A;ID;0x1f019f;;;BA)(A;ID;0x1f019f;;;SY)(A;ID;FA;;;${userSid})"
$repair = Get-PlatformTaskAclRepair $broken
Assert-Equal $repair.Changed $true 'Missing scheduler rights detected'
$before = [Security.AccessControl.RawSecurityDescriptor]::new($broken)
$after = [Security.AccessControl.RawSecurityDescriptor]::new($repair.Dacl)
Assert-Equal $after.DiscretionaryAcl.Count ($before.DiscretionaryAcl.Count + 2) 'Only two additional ACEs'
foreach ($ace in @($after.DiscretionaryAcl[0], $after.DiscretionaryAcl[1])) {
    Assert-Equal $ace.AccessMask 0x60 'Only missing standard rights granted'
    Assert-Equal $ace.AceFlags ([Security.AccessControl.AceFlags]::None) 'No inheritance to other tasks'
    if ($ace.SecurityIdentifier.Value -notin @('S-1-5-18', 'S-1-5-32-544')) { throw 'Unexpected trustee' }
}
for ($i = 0; $i -lt $before.DiscretionaryAcl.Count; $i++) {
    Assert-Equal (Get-AceBytes $after.DiscretionaryAcl[$i + 2]) (Get-AceBytes $before.DiscretionaryAcl[$i]) 'Original ACE preserved byte for byte'
}
Assert-Equal (Get-PlatformTaskAclRepair $repair.Dacl).Changed $false 'Repair is idempotent'
foreach ($rights in @('FA', 'GA')) {
    Assert-Equal (Get-PlatformTaskAclRepair "D:(A;;${rights};;;SY)(A;;${rights};;;BA)").Changed $false 'Full rights already present'
}
$generic = Get-PlatformTaskAclRepair 'D:(A;;GRGWGX;;;SY)(A;;FA;;;BA)'
$genericAcl = [Security.AccessControl.RawSecurityDescriptor]::new($generic.Dacl)
Assert-Equal $genericAcl.DiscretionaryAcl[0].AccessMask 0xd0040 'Generic file rights mapped correctly'
Assert-Equal (Get-PlatformTaskAclRepair 'D:(A;OIIO;FA;;;SY)(A;;FA;;;BA)').Changed $true 'Inherit-only ACE does not grant this task rights'
Assert-Throws { Get-PlatformTaskAclRepair 'D:(D;;GX;;;SY)(A;;FA;;;BA)' } '*deny ACE*'
Assert-Throws { Get-PlatformTaskAclRepair 'D:(D;;GX;;;AU)(A;;FA;;;SY)(A;;FA;;;BA)' } '*deny ACE*'
Assert-Throws { Get-PlatformTaskAclRepair 'O:SYG:SYD:NO_ACCESS_CONTROL' } '*null DACL*'

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('inserter-acl-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    $task = New-FakeTask $broken
    Repair-PlatformTaskPermissions -Task $task -TaskName $task.Name -RepoPath $testRoot -Port 8780
    Assert-Equal $task.SetCount 1 'One scoped ACL update'
    $updated = [Security.AccessControl.RawSecurityDescriptor]::new($task.Sddl)
    Assert-Equal $updated.Owner.Value $before.Owner.Value 'Owner preserved'
    Assert-Equal $updated.Group.Value $before.Group.Value 'Group preserved'
    Assert-Equal $task.RunCount 0 'ACL repair does not launch task'
    $backups = @(Get-ChildItem -LiteralPath (Join-Path $testRoot 'data\deploy-backups') -Filter '*.sddl')
    Assert-Equal $backups.Count 1 'ACL backup created'
    Assert-Equal (Get-Content -LiteralPath $backups[0].FullName -Raw).Trim() $broken 'Original ACL backed up'
    Repair-PlatformTaskPermissions -Task $task -TaskName $task.Name -RepoPath $testRoot -Port 8780
    Assert-Equal $task.SetCount 1 'No repeated mutation'

    foreach ($badName in @('Other task', 'MSX*', 'Folder\MSX', '')) {
        Assert-Throws { Repair-PlatformTaskPermissions -Task $task -TaskName $badName -RepoPath $testRoot -Port 8780 } '*Unexpected task path*'
    }
    $task = New-FakeTask $broken
    $task.ConcurrentChange = $true
    Assert-Throws { Repair-PlatformTaskPermissions -Task $task -TaskName $task.Name -RepoPath $testRoot -Port 8780 } '*concurrently*'
    Assert-Equal $task.SetCount 0 'Concurrent changes not overwritten'
    $task = New-FakeTask $broken
    $task.IgnoreWrite = $true
    Assert-Throws { Repair-PlatformTaskPermissions -Task $task -TaskName $task.Name -RepoPath $testRoot -Port 8780 } '*verification failed*'

    $task = New-FakeTask $repair.Dacl
    Start-PlatformTaskChecked -Task $task -TimeoutSeconds 0
    Assert-Equal $task.RunCount 1 'Start succeeds with real running instance'
    $task.InstanceState = 3
    Assert-Throws { Start-PlatformTaskChecked -Task $task -TimeoutSeconds 0 } '*accepted start but has no running process*'
    $task.InstanceState = 4
    $task.InstancePid = 0
    Assert-Throws { Start-PlatformTaskChecked -Task $task -TimeoutSeconds 0 } '*accepted start but has no running process*'
    $task.RefreshFailure = $true
    Assert-Throws { Start-PlatformTaskChecked -Task $task -TimeoutSeconds 0 } '*accepted start but has no running process*'
    $task.Enabled = $false
    $previousRuns = $task.RunCount
    Assert-Throws { Start-PlatformTaskChecked -Task $task -TimeoutSeconds 0 } '*disabled*'
    Assert-Equal $task.RunCount $previousRuns 'Disabled task not started'
    $task.Enabled = $true
    $task.Definition.Settings.MultipleInstances = 0
    Assert-Throws { Start-PlatformTaskChecked -Task $task -TimeoutSeconds 0 } '*IgnoreNew*'
    Assert-Equal $task.RunCount $previousRuns 'Unsafe duplicate policy not started'
} finally {
    # Delete only the exact GUID test directory created above.
    $resolved = [IO.Path]::GetFullPath($testRoot)
    if ((Split-Path $resolved -Leaf) -notmatch '^inserter-acl-test-[a-f0-9]{32}$' -or
        (Split-Path $resolved -Parent).TrimEnd('\') -ne ([IO.Path]::GetTempPath()).TrimEnd('\')) {
        throw 'Unexpected cleanup target'
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Host 'Task ACL and start checks passed. No scheduled tasks or system policies changed.'
