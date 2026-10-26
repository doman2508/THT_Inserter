$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$diagnostic = Join-Path $repo 'diagnose_platform_task_8780.ps1'
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($diagnostic, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { throw ($errors | Out-String) }

# Loading functions must not query or modify a production task.
$loadOutput = @(. $diagnostic -FunctionsOnly *>&1)
if ($loadOutput.Count) { throw 'Library load unexpectedly produced diagnostic output' }
Initialize-InserterDiagnosticNative
$blocked = $false
try { [InserterTaskDiagnostic.ReadOnlyPolicy]::AssignedSids('SeDebugPrivilege') } catch {
    if ($_.Exception.GetBaseException().Message -notlike 'Only batch logon rights*') { throw }
    $blocked = $true
}
if (-not $blocked) { throw 'Policy read whitelist failed' }

# Inspect the native boundary to prevent accidentally adding a mutation API.
$expected = @('LsaOpenPolicy', 'LsaEnumerateAccountsWithUserRight', 'LsaNtStatusToWinError',
    'LsaFreeMemory', 'LsaClose', 'NetUserGetLocalGroups', 'NetApiBufferFree')
$nativeMethods = @([InserterTaskDiagnostic.ReadOnlyPolicy].GetMethods(
    [Reflection.BindingFlags]'NonPublic,Static') | Where-Object {
        $_.GetCustomAttributes([Runtime.InteropServices.DllImportAttribute], $false).Count -gt 0
    } | ForEach-Object Name)
if (@(Compare-Object $expected $nativeMethods).Count) { throw 'Unexpected native API boundary' }

# Read-only live probe: both an explicit read failure and a list are valid
# on a non-admin test host, but a silent result is not.
foreach ($right in @('SeBatchLogonRight', 'SeDenyBatchLogonRight')) {
    $report = (& { Show-InserterBatchAssignments $right } 6>&1 | Out-String)
    if ($report -notlike "*${right}:*" -or
        $report -notmatch '(READ FAILED:|NONE \(read succeeded|S-1-)') {
        throw "No explicit diagnostic result for $right"
    }
}
Write-Host 'Diagnostic tests OK: PS5 syntax/native compilation, read-only API whitelist, explicit results; no task changes.'
