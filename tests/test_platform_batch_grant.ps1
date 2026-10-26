$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$scriptPath = Join-Path $repo 'grant_platform_batch_logon_8780.ps1'
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { throw ($errors | Out-String) }
$loadOutput = @(. $scriptPath -FunctionsOnly *>&1)
if ($loadOutput.Count) { throw 'Library load unexpectedly performed work' }
Initialize-InserterBatchGrantNative

$scope = @{ComputerName='WIN-OGJFAFPNMCU'; TaskPath='\MSX THT Inserter 8780'; AccountSid='S-1-5-21-2668147273-1832477435-4174271069-1019'}
Assert-InserterBatchGrantTarget @scope
foreach ($key in @('ComputerName', 'TaskPath', 'AccountSid')) {
    $invalid = $scope.Clone()
    $invalid[$key] = 'different-target'
    $blocked = $false
    try { Assert-InserterBatchGrantTarget @invalid } catch {
        if ($_.Exception.Message -notlike 'Unexpected server*') { throw }
        $blocked = $true
    }
    if (-not $blocked) { throw "Wrong $key was accepted" }
}
if (-not (Test-InserterSidSetEqual @() @())) { throw 'Empty sets should match' }
if (-not (Test-InserterSidSetEqual @('S-1-5-18','S-1-5-32-544') @('S-1-5-32-544','S-1-5-18','S-1-5-18'))) { throw 'Set comparison must ignore order/duplicates' }
if (Test-InserterSidSetEqual @('S-1-5-18') @('S-1-5-18','S-1-5-32-544')) { throw 'Additional assignment was not detected' }
if (Test-InserterSidSetEqual @('S-1-5-18') @()) { throw 'Removed assignment was not detected' }

$expectedApis = @('LsaOpenPolicy','LsaAddAccountRights','LsaNtStatusToWinError','LsaClose')
$actualApis = @([InserterTaskSetup.BatchLogonGrant].GetMethods([Reflection.BindingFlags]'NonPublic,Static') |
    Where-Object { $_.GetCustomAttributes([Runtime.InteropServices.DllImportAttribute], $false).Count -gt 0 } | ForEach-Object Name)
if (@(Compare-Object $expectedApis $actualApis).Count) { throw 'Unexpected mutation API boundary' }
$grantMethod = [InserterTaskSetup.BatchLogonGrant].GetMethod('GrantRemote01')
if ($grantMethod.GetParameters().Count -ne 0) { throw 'Grant must not accept arbitrary accounts/rights' }
# Never invoke the native mutation from tests, including on the real server.
Write-Host 'Batch grant tests OK: syntax/compilation, exact scope, set verification, additive API boundary. NO rights changed.'
