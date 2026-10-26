param([switch]$FunctionsOnly)

$ErrorActionPreference = 'Stop'

function Assert-InserterBatchGrantTarget {
    param([string]$ComputerName, [string]$TaskPath, [string]$AccountSid)
    if ($ComputerName -ne 'WIN-OGJFAFPNMCU' -or $TaskPath -ne '\MSX THT Inserter 8780' -or
        $AccountSid -ne 'S-1-5-21-2668147273-1832477435-4174271069-1019') {
        throw 'Unexpected server, task or account SID. No account rights were changed.'
    }
}

function Test-InserterSidSetEqual {
    param([string[]]$Left, [string[]]$Right)
    return ((@($Left | Sort-Object -Unique) -join ',') -eq (@($Right | Sort-Object -Unique) -join ','))
}

function Initialize-InserterBatchGrantNative {
    if ('InserterTaskSetup.BatchLogonGrant' -as [type]) { return }
    Add-Type @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;
namespace InserterTaskSetup {
 public static class BatchLogonGrant {
  [StructLayout(LayoutKind.Sequential)] struct OA {
   public uint Length; public IntPtr RootDirectory, ObjectName; public uint Attributes;
   public IntPtr SecurityDescriptor, SecurityQualityOfService;
  }
  [StructLayout(LayoutKind.Sequential)] struct US {
   public ushort Length, MaximumLength; public IntPtr Buffer;
  }
  [DllImport("advapi32.dll")] static extern uint LsaOpenPolicy(IntPtr name, ref OA attrs, uint access, out IntPtr handle);
  [DllImport("advapi32.dll")] static extern uint LsaAddAccountRights(IntPtr handle, byte[] sid, ref US right, uint count);
  [DllImport("advapi32.dll")] static extern uint LsaNtStatusToWinError(uint status);
  [DllImport("advapi32.dll")] static extern uint LsaClose(IntPtr handle);
  static void Check(uint status, string operation) {
   if (status != 0) {
    int code = (int)LsaNtStatusToWinError(status);
    throw new Win32Exception(code, operation + ": Win32=" + code + "; " + new Win32Exception(code).Message);
   }
  }
  // Deliberately no account/right arguments: this one-time repair may only
  // add the single approved right to the single approved production account.
  public static void GrantRemote01() {
   if (!String.Equals(Environment.MachineName, "WIN-OGJFAFPNMCU", StringComparison.OrdinalIgnoreCase))
    throw new InvalidOperationException("Unexpected server; no account rights were changed.");
   SecurityIdentifier sid = (SecurityIdentifier)new NTAccount("WIN-OGJFAFPNMCU", "Remote01").Translate(typeof(SecurityIdentifier));
   if (sid.Value != "S-1-5-21-2668147273-1832477435-4174271069-1019")
    throw new InvalidOperationException("Unexpected Remote01 SID; no account rights were changed.");
   using (WindowsIdentity identity = WindowsIdentity.GetCurrent()) {
    if (!new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator))
     throw new InvalidOperationException("Run this one-time repair as administrator.");
   }
   OA attrs = new OA(); attrs.Length = (uint)Marshal.SizeOf(typeof(OA));
   IntPtr handle = IntPtr.Zero, text = IntPtr.Zero;
   try {
    // POLICY_LOOKUP_NAMES | POLICY_CREATE_ACCOUNT (LSA policy record, not a Windows user).
    Check(LsaOpenPolicy(IntPtr.Zero, ref attrs, 0x810, out handle), "LsaOpenPolicy");
    const string rightName = "SeBatchLogonRight";
    text = Marshal.StringToHGlobalUni(rightName);
    US right = new US { Buffer=text, Length=(ushort)(rightName.Length*2), MaximumLength=(ushort)((rightName.Length+1)*2) };
    byte[] bytes = new byte[sid.BinaryLength]; sid.GetBinaryForm(bytes, 0);
    // Additive/idempotent: never replace the assignment list or remove other rights.
    Check(LsaAddAccountRights(handle, bytes, ref right, 1), "LsaAddAccountRights");
   } finally {
    if (text != IntPtr.Zero) Marshal.FreeHGlobal(text);
    if (handle != IntPtr.Zero) LsaClose(handle);
   }
  }
 }
}
'@
}

if ($FunctionsOnly) { return }

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this one-time repair in an administrator PowerShell. Nothing was changed.'
}
$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$task = $service.GetFolder('\').GetTask('MSX THT Inserter 8780')
$taskUser = $task.Definition.Principal.UserId
$sidText = $taskUser
if ($sidText -notmatch '^S-1-') {
    $sidText = ([Security.Principal.NTAccount]::new($taskUser)).Translate([Security.Principal.SecurityIdentifier]).Value
}
Assert-InserterBatchGrantTarget -ComputerName $env:COMPUTERNAME -TaskPath $task.Path -AccountSid $sidText

. (Join-Path $PSScriptRoot 'diagnose_platform_task_8780.ps1') -FunctionsOnly
Initialize-InserterDiagnosticNative
$beforeAllow = @([InserterTaskDiagnostic.ReadOnlyPolicy]::AssignedSids('SeBatchLogonRight'))
$beforeDeny = @([InserterTaskDiagnostic.ReadOnlyPolicy]::AssignedSids('SeDenyBatchLogonRight'))
# The diagnosed server has no batch-deny assignments. Do not work around any
# new deny policy, including group assignments, without administrator review.
if ($beforeDeny.Count -ne 0) { throw 'Batch deny assignments are present; administrator review required. Nothing was changed.' }
if ($beforeAllow -contains $sidText) {
    Write-Host 'SeBatchLogonRight is already assigned to Remote01. No changes needed.'
    return
}

$backupDir = Join-Path $PSScriptRoot 'data\deploy-backups'
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$backupPath = Join-Path $backupDir ('batch-logon-{0}.json' -f [guid]::NewGuid().ToString('N'))
[pscustomobject]@{
    RecordedAt = [DateTimeOffset]::Now.ToString('o')
    Computer = $env:COMPUTERNAME
    TaskPath = $task.Path
    TargetSid = $sidText
    Right = 'SeBatchLogonRight'
    PreviousAllowSids = $beforeAllow
    PreviousDenySids = $beforeDeny
} | ConvertTo-Json -Depth 3 | Out-File -LiteralPath $backupPath -Encoding utf8
Write-Host "Previous assignments recorded: $backupPath"

$currentAllow = @([InserterTaskDiagnostic.ReadOnlyPolicy]::AssignedSids('SeBatchLogonRight'))
$currentDeny = @([InserterTaskDiagnostic.ReadOnlyPolicy]::AssignedSids('SeDenyBatchLogonRight'))
if (-not (Test-InserterSidSetEqual $beforeAllow $currentAllow) -or
    -not (Test-InserterSidSetEqual $beforeDeny $currentDeny)) {
    throw 'Policy changed concurrently. No account rights were changed by this script.'
}
Initialize-InserterBatchGrantNative
[InserterTaskSetup.BatchLogonGrant]::GrantRemote01()
$afterAllow = @([InserterTaskDiagnostic.ReadOnlyPolicy]::AssignedSids('SeBatchLogonRight'))
$afterDeny = @([InserterTaskDiagnostic.ReadOnlyPolicy]::AssignedSids('SeDenyBatchLogonRight'))
if (-not (Test-InserterSidSetEqual (@($beforeAllow) + $sidText) $afterAllow) -or
    -not (Test-InserterSidSetEqual $beforeDeny $afterDeny)) {
    throw 'Post-change verification failed or policy changed concurrently. App was not stopped; review the saved assignments.'
}
Write-Host "SUCCESS: added only SeBatchLogonRight to WIN-OGJFAFPNMCU\Remote01 ($sidText)."
Write-Host 'Other assignments preserved. No group membership, task credentials, logging or processes changed.'
Write-Host 'The running app was not restarted. A normal deploy can now verify background startup.'
