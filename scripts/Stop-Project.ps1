[CmdletBinding()]
param()
. "$PSScriptRoot/Project.ps1"
$config = Get-ProjectConfig
$linuxRoot = Get-LinuxProjectRoot $config
Assert-ProjectDistribution $config $linuxRoot
Invoke-Checked 'wsl.exe' @('-d',$config.wslDistribution,'-u',$config.linuxUser,'--exec','bash',"$linuxRoot/scripts/stop-linux.sh")
foreach ($script in @('windows_host.py','gta_road_context.py','ui_overlay.py','control_panel.py','xbox_mapper.py')) {
    Find-ProjectPythonProcess $script | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
}
Write-Output 'Bridge stopped. GTA remains open; the native freshness watchdog releases automatic controls.'
