$ErrorActionPreference='Stop'
. "$PSScriptRoot/Project.ps1"
$config=Get-ProjectConfig
Initialize-ProjectDirectories
$root=$ProjectRoot
# Elevate only when the user configured an elevated GTA/Steam installation.
$administrator=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($config.elevateControls -and !$administrator) {
    # -Wait waits for the entire process tree, including the long-lived panel.
    # Wait only for the elevated readiness-check process to finish instead.
    $launcher=Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -PassThru -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $launcher.WaitForExit()
    if ($launcher.ExitCode -ne 0) { throw 'Elevated control panel launcher failed.' }
    return
}
if (-not ('GTAControlPanelWindow' -as [type])) {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class GTAControlPanelWindow {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left,Top,Right,Bottom; }
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] private static extern IntPtr FindWindow(string cls,string title);
  public static IntPtr FindPanel() { return FindWindow(null,"NMK AI Driving Controls"); }
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr window);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window,out RECT rect);
  [DllImport("user32.dll",SetLastError=true)] public static extern bool PostMessageW(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);
}
"@
}
$title='NMK AI Driving Controls'
$window=[GTAControlPanelWindow]::FindPanel()
if ($window -ne [IntPtr]::Zero) {
    $rect=New-Object GTAControlPanelWindow+RECT
    $null=[GTAControlPanelWindow]::GetWindowRect($window,[ref]$rect)
    # Keep an already visible panel exactly where the user put it. A runtime
    # restart must not repeatedly manipulate a healthy Tk window.
    if ([GTAControlPanelWindow]::IsIconic($window) -or
        ![GTAControlPanelWindow]::IsWindowVisible($window) -or ($rect.Bottom - $rect.Top) -lt 400) {
        if (![GTAControlPanelWindow]::PostMessageW($window,0x805b,[IntPtr]::Zero,[IntPtr]::Zero)) {
            throw 'Could not deliver the control panel restore request.'
        }
    }
} else {
    Start-Process "$root/.venv/Scripts/pythonw.exe" -WindowStyle Hidden -WorkingDirectory $root -ArgumentList "`"$root/bridge/control_panel.py`""
}
# Do not announce success merely because a launcher process was created.
$deadline=(Get-Date).AddSeconds(8)
do {
    $window=[GTAControlPanelWindow]::FindPanel()
    $rect=New-Object GTAControlPanelWindow+RECT
    $null=[GTAControlPanelWindow]::GetWindowRect($window,[ref]$rect)
    $ready=$window -ne [IntPtr]::Zero -and [GTAControlPanelWindow]::IsWindowVisible($window) -and
        ![GTAControlPanelWindow]::IsIconic($window) -and ($rect.Bottom - $rect.Top) -gt 400
    if (!$ready) { Start-Sleep -Milliseconds 100 }
} until ($ready -or (Get-Date) -gt $deadline)
if (!$ready) { throw 'The NMK Ai control panel did not become visible. Check reports/control-panel.log.' }
@{ ready=$true; window=$window.ToInt64(); checked=(Get-Date).ToString('o') } |
    ConvertTo-Json | Set-Content -LiteralPath "$root/reports/control-panel-ready.json"
