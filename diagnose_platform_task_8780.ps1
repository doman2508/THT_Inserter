param([switch]$FunctionsOnly)

$ErrorActionPreference = 'Stop'

function Initialize-InserterDiagnosticNative {
    if ('InserterTaskDiagnostic.ReadOnlyPolicy' -as [type]) { return }
    # Read-only APIs only: no credential access, logon attempt or policy update.
    Add-Type @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;
namespace InserterTaskDiagnostic {
 public static class ReadOnlyPolicy {
  [StructLayout(LayoutKind.Sequential)] struct OA {
   public uint Length; public IntPtr RootDirectory, ObjectName; public uint Attributes;
   public IntPtr SecurityDescriptor, SecurityQualityOfService;
  }
  [StructLayout(LayoutKind.Sequential)] struct US {
   public ushort Length, MaximumLength; public IntPtr Buffer;
  }
  [DllImport("advapi32.dll")] static extern uint LsaOpenPolicy(IntPtr name, ref OA attrs, uint access, out IntPtr handle);
  [DllImport("advapi32.dll")] static extern uint LsaEnumerateAccountsWithUserRight(IntPtr handle, ref US right, out IntPtr buffer, out uint count);
  [DllImport("advapi32.dll")] static extern uint LsaNtStatusToWinError(uint status);
  [DllImport("advapi32.dll")] static extern uint LsaFreeMemory(IntPtr buffer);
  [DllImport("advapi32.dll")] static extern uint LsaClose(IntPtr handle);
  [DllImport("netapi32.dll", CharSet=CharSet.Unicode)] static extern uint NetUserGetLocalGroups(string server, string user, uint level, uint flags, out IntPtr buffer, uint maxLength, out uint read, out uint total);
  [DllImport("netapi32.dll")] static extern uint NetApiBufferFree(IntPtr buffer);

  static void CheckLsa(uint status, string operation) {
   if (status != 0) {
    int code = (int)LsaNtStatusToWinError(status);
    throw new Win32Exception(code, operation + ": Win32=" + code + ", NTSTATUS=0x" + status.ToString("X8") + "; " + new Win32Exception(code).Message);
   }
  }
  public static string[] AssignedSids(string rightName) {
   if (rightName != "SeBatchLogonRight" && rightName != "SeDenyBatchLogonRight")
    throw new ArgumentException("Only batch logon rights may be read by this diagnostic.");
   OA attrs = new OA(); attrs.Length = (uint)Marshal.SizeOf(typeof(OA));
   IntPtr handle = IntPtr.Zero, buffer = IntPtr.Zero, text = IntPtr.Zero;
   try {
    CheckLsa(LsaOpenPolicy(IntPtr.Zero, ref attrs, 0x801, out handle), "LsaOpenPolicy");
    text = Marshal.StringToHGlobalUni(rightName);
    US right = new US { Buffer=text, Length=(ushort)(rightName.Length*2), MaximumLength=(ushort)((rightName.Length+1)*2) };
    uint count;
    uint status = LsaEnumerateAccountsWithUserRight(handle, ref right, out buffer, out count);
    if (status == 0x8000001A) return new string[0]; // STATUS_NO_MORE_ENTRIES, not a read failure.
    CheckLsa(status, "LsaEnumerateAccountsWithUserRight");
    string[] results = new string[count];
    for (int i=0; i<count; i++) results[i] = new SecurityIdentifier(Marshal.ReadIntPtr(buffer, i*IntPtr.Size)).Value;
    return results;
   } finally {
    if (buffer != IntPtr.Zero) LsaFreeMemory(buffer);
    if (text != IntPtr.Zero) Marshal.FreeHGlobal(text);
    if (handle != IntPtr.Zero) LsaClose(handle);
   }
  }
  public static string[] LocalGroups(string user) {
   IntPtr buffer = IntPtr.Zero;
   try {
    uint read, total;
    uint status = NetUserGetLocalGroups(null, user, 0, 1, out buffer, uint.MaxValue, out read, out total);
    if (status != 0) throw new Win32Exception((int)status, "NetUserGetLocalGroups: Win32=" + status);
    string[] results = new string[read];
    for (int i=0; i<read; i++) results[i] = Marshal.PtrToStringUni(Marshal.ReadIntPtr(buffer, i*IntPtr.Size));
    return results;
   } finally { if (buffer != IntPtr.Zero) NetApiBufferFree(buffer); }
  }
 }
}
'@
}

function Show-InserterBatchAssignments {
    param([string]$RightName)
    Write-Host "`n${RightName}:"
    try {
        $sids = @([InserterTaskDiagnostic.ReadOnlyPolicy]::AssignedSids($RightName))
        if ($sids.Count -eq 0) { Write-Host '  NONE (read succeeded; no direct assignments)'; return }
        foreach ($sidText in $sids) {
            $sid = [Security.Principal.SecurityIdentifier]::new($sidText)
            try { $name = $sid.Translate([Security.Principal.NTAccount]).Value } catch { $name = '<unresolved SID>' }
            Write-Host "  $sidText | $name"
        }
    } catch { Write-Host "  READ FAILED: $($_.Exception.GetBaseException().Message)" }
}

if ($FunctionsOnly) { return }

Write-Host 'BEGIN INSERTER READ-ONLY DIAGNOSTIC'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
Write-Host "Administrator=$($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)); Computer=$env:COMPUTERNAME"
Write-Host 'No tasks, credentials, permissions, logging settings or processes will be changed.'
$taskName = 'MSX THT Inserter 8780'
try {
    $service = New-Object -ComObject 'Schedule.Service'
    $service.Connect()
    $task = $service.GetFolder('\').GetTask($taskName)
    $taskSidText = $task.Definition.Principal.UserId
    if ($taskSidText -notmatch '^S-1-') {
        $taskSidText = ([Security.Principal.NTAccount]::new($taskSidText)).Translate([Security.Principal.SecurityIdentifier]).Value
    }
    $taskAccount = ([Security.Principal.SecurityIdentifier]::new($taskSidText)).Translate([Security.Principal.NTAccount]).Value
    Write-Host "TaskAccount=$taskAccount; SID=$taskSidText; LogonType=$($task.Definition.Principal.LogonType)"
    Write-Host "State=$($task.State); LastRun=$($task.LastRunTime.ToString('s')); LastResult=$($task.LastTaskResult) (may be stale)"
} catch { Write-Host "TASK READ FAILED: $($_.Exception.GetBaseException().Message)" }

try {
    Initialize-InserterDiagnosticNative
    if ($taskAccount) {
        Write-Host "`nLocal groups of task account (including indirect membership):"
        try {
            $groups = @([InserterTaskDiagnostic.ReadOnlyPolicy]::LocalGroups($taskAccount))
            if ($groups.Count -eq 0) { Write-Host '  NONE' }
            foreach ($group in $groups) {
                $groupSid = ([Security.Principal.NTAccount]::new($group)).Translate([Security.Principal.SecurityIdentifier]).Value
                Write-Host "  $groupSid | $group"
            }
        } catch { Write-Host "  GROUP READ FAILED: $($_.Exception.GetBaseException().Message)" }
    }
    Show-InserterBatchAssignments 'SeBatchLogonRight'
    Show-InserterBatchAssignments 'SeDenyBatchLogonRight'
    Write-Host 'Assignments above are direct. Group membership must also be considered; this is not a password validation.'
} catch { Write-Host "POLICY DIAGNOSTIC FAILED: $($_.Exception.GetBaseException().Message)" }

$logName = 'Microsoft-Windows-TaskScheduler/Operational'
Write-Host "`nTask history:"
try {
    $log = Get-WinEvent -ListLog $logName -ErrorAction Stop
    Write-Host "  Enabled=$($log.IsEnabled); TotalRecords=$($log.RecordCount)"
    if ($log.IsEnabled) {
        try {
            $events = @(Get-WinEvent -LogName $logName -FilterXPath "*[EventData[Data[@Name='TaskName']='\MSX THT Inserter 8780']]" -MaxEvents 8 -ErrorAction Stop)
            foreach ($event in $events) { Write-Host "$($event.TimeCreated.ToString('s')) ID=$($event.Id)`n$($event.Message)" }
        } catch {
            if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') { Write-Host '  NO MATCHING EVENTS for Inserter.' }
            else { Write-Host "  EVENT READ FAILED: $($_.Exception.GetBaseException().Message)" }
        }
    } else { Write-Host '  History is disabled. It has NOT been enabled by this script.' }
} catch { Write-Host "  LOG READ FAILED: $($_.Exception.GetBaseException().Message)" }

try {
    $health = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8780/api/health' -TimeoutSec 3
    Write-Host "`nHTTP health=$($health.StatusCode)"
} catch { Write-Host "`nHTTP health FAILED: $($_.Exception.GetBaseException().Message)" }
Write-Host 'END INSERTER READ-ONLY DIAGNOSTIC'
