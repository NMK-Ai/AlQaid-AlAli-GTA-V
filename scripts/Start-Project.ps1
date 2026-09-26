[CmdletBinding()]
param()
. "$PSScriptRoot/Project.ps1"
$config = Get-ProjectConfig
Initialize-ProjectDirectories
foreach ($required in @('.venv/Scripts/python.exe','runtime/bridge-token','runtime/game-install.json','runtime/linux-ready.json','config/local.json')) {
    if (!(Test-Path -LiteralPath (Join-Path $ProjectRoot $required))) { throw "Missing $required. Complete Setup and Install-GameBridge first." }
}
$linuxRoot = Get-LinuxProjectRoot $config
Assert-ProjectDistribution $config $linuxRoot
$title = "NMK Ai ($($config.wslDistribution))"
$ui = Get-Process msrdc -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle.Contains($title) }
if ($ui -and $ui.MainWindowTitle -like '*WARN:COPY MODE*') {
    throw 'WSLg graphics failed. Stop this project, save work in other WSL distributions, then restart WSL. See docs/TROUBLESHOOTING.md.'
}
if (!$ui) {
    $linux = Start-ProjectProcess 'wsl.exe' @('-d',$config.wslDistribution,'-u',$config.linuxUser,'--exec','bash',"$linuxRoot/scripts/run-linux.sh") 'linux-supervisor'
    $deadline = (Get-Date).AddSeconds(60)
    do {
        Start-Sleep -Milliseconds 500
        $ui = Get-Process msrdc -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle.Contains($title) }
    } until ($ui -or (Get-Date) -gt $deadline -or $linux.HasExited)
    if (!$ui) { throw 'NMK Ai UI did not start. See reports/linux-supervisor-error.log and reports/frogpilot-manager-cuda.log.' }
}
& "$PSScriptRoot/Show-NMKAi.ps1"
if (!(Get-Process GTA5_Enhanced -ErrorAction SilentlyContinue)) {
    $null = Start-ProjectProcess $config.steamExecutable @('-applaunch',$config.steamAppId,'-nobattleye','-windowed','-width','1928','-height','1208')
}
$deadline = (Get-Date).AddSeconds(120)
do {
    $game = Get-Process GTA5_Enhanced -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -and $_.MainWindowTitle -eq 'Grand Theft Auto V' }
    if (!$game) { Start-Sleep -Milliseconds 500 }
} until ($game -or (Get-Date) -gt $deadline)
if (!$game) { throw 'GTA has not opened. Check Steam/Rockstar, then run Start-NMKAi.cmd again.' }
if (!(Find-ProjectPythonProcess 'windows_host.py')) {
    $addresses = & wsl.exe -d $config.wslDistribution --exec hostname -I
    if ($LASTEXITCODE -ne 0 -or !$addresses) { throw 'Cannot get WSL address.' }
    $address = (($addresses | Out-String).Trim() -split '\s+')[0]
    $null = Start-ProjectProcess "$ProjectRoot/.venv/Scripts/python.exe" @('-X','utf8',"$ProjectRoot/bridge/windows_host.py",'--host',$address) 'windows-host'
}
& "$PSScriptRoot/Start-ControlPanel.ps1"
if (!(Find-ProjectPythonProcess 'xbox_mapper.py')) {
    $null = Start-ProjectProcess "$ProjectRoot/.venv/Scripts/pythonw.exe" @('"' + "$ProjectRoot/bridge/xbox_mapper.py" + '"') 'xbox-mapper'
}
& "$PSScriptRoot/Start-RoadContext.ps1"
$overlayPath = Join-Path $ProjectRoot 'runtime/ui-overlay.json'
if ((Test-Path -LiteralPath $overlayPath) -and (Get-Content -LiteralPath $overlayPath -Raw | ConvertFrom-Json).enabled) {
    & "$PSScriptRoot/Start-UIOverlay.ps1"
}
Write-Output 'Windows opened. Load Story Mode, spawn the Krieger, and use the driving panel. Setup does not engage driving.'
