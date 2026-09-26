. "$PSScriptRoot/Project.ps1"
$config=Get-ProjectConfig
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class NMKAiWindow {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
'@
[NMKAiWindow]::SetProcessDPIAware() | Out-Null
$window = Get-Process msrdc -ErrorAction SilentlyContinue | Where-Object MainWindowTitle -Match ('(ui|FrogPilot) \('+[regex]::Escape($config.wslDistribution)+'\)') | Select-Object -First 1
if (!$window) { throw 'NMK Ai UI is not running. Start the project first.' }
if ($window.MainWindowTitle -like '*WARN:COPY MODE*') {
  throw 'WSLg failed to initialize shared graphics memory. Restart the project Linux environment; moving this invisible window cannot fix it.'
}
[NMKAiWindow]::ShowWindowAsync($window.MainWindowHandle, 9) | Out-Null
# Let WSLg own window geometry. Moving its RDP proxy with SetWindowPos moved
# the image without updating X11's input origin (491-pixel mismatch observed).
# Ordinary title-bar dragging is handled by WSLg and keeps both sides aligned.
[NMKAiWindow]::SetForegroundWindow($window.MainWindowHandle) | Out-Null
