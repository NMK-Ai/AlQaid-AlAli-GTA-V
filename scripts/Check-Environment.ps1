[CmdletBinding()]
param()
. "$PSScriptRoot/Project.ps1"
$config = Get-ProjectConfig
Initialize-ProjectDirectories
$checks = @()
foreach ($tool in @('git.exe','cmake.exe','wsl.exe')) {
    $checks += @{name=$tool;ok=[bool](Get-Command $tool -ErrorAction SilentlyContinue)}
}
$checks += @{name='GTA Enhanced configured';ok=[bool]($config.gameDirectory -and (Test-Path -LiteralPath (Join-Path $config.gameDirectory $config.gameExecutable)))}
foreach ($path in @('.venv/Scripts/python.exe','vendor/ScriptHookV_SDK/inc/main.h','vendor/ScriptHookV_runtime/bin/ScriptHookV.dll','vendor/ScriptHookV_runtime/bin/xinput1_4.dll','build/native/Release/OpenPilotGTA.asi','runtime/game-install.json','runtime/linux-ready.json','runtime/bridge-token')) {
    $checks += @{name=$path;ok=(Test-Path -LiteralPath (Join-Path $ProjectRoot $path))}
}
$report = [ordered]@{
    checkedUtc=[DateTime]::UtcNow.ToString('o');distribution=$config.wslDistribution
    checks=$checks;gpu=@(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion)
    memoryGiB=[Math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1)
    note='Prerequisites only. Successful setup does not establish adequate frame rate or driving quality.'
}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$ProjectRoot/reports/environment.json" -Encoding UTF8
$checks | ForEach-Object { '{0} {1}' -f $(if ($_.ok) {'OK  '} else {'MISS'}),$_.name }
if (@($checks | Where-Object { !$_.ok }).Count) { exit 1 }
