[CmdletBinding()]
param(
    [string]$GameDirectory,
    [ValidateSet('All','Configure','Windows','Native','Linux')][string]$Stage='All',
    [string]$PythonExe,
    [string]$RootfsPath,
    [switch]$Plan
)
. "$PSScriptRoot/Project.ps1"
$config = Get-ProjectConfig
if ($GameDirectory) { $config.gameDirectory = [IO.Path]::GetFullPath($GameDirectory) }
if ($Plan) {
    [pscustomobject]@{
        project=$ProjectRoot; game=$config.gameDirectory; distribution=$config.wslDistribution; stage=$Stage
        actions='Create local config/token; build Windows adapter; import owned Ubuntu 24.04; build pinned FrogPilot and Macrostiff. Install game files separately.'
        requirements='Windows 11 x64, WSL2/WSLg, NVIDIA Windows driver, Python 3.13 x64 with Tk, Git, CMake, Visual Studio 2022 C++ Build Tools, Script Hook V SDK/runtime'
    } | Format-List
    return
}
Initialize-ProjectDirectories
$steam = Get-ItemProperty 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue
if (!$config.steamExecutable -and $steam -and $steam.SteamExe) { $config.steamExecutable = $steam.SteamExe.Replace('/','\') }
if (!$config.gameDirectory -and $config.steamExecutable) {
    $steamRoot = Split-Path -Parent $config.steamExecutable
    $libraries = @($steamRoot)
    $vdf = Join-Path $steamRoot 'steamapps/libraryfolders.vdf'
    if (Test-Path -LiteralPath $vdf) {
        foreach ($match in [regex]::Matches((Get-Content -LiteralPath $vdf -Raw), '"path"\s+"([^"]+)"')) {
            $libraries += $match.Groups[1].Value.Replace('\\','\')
        }
    }
    foreach ($library in $libraries) {
        $candidate = Join-Path $library 'steamapps/common/Grand Theft Auto V Enhanced'
        if (Test-Path -LiteralPath (Join-Path $candidate $config.gameExecutable)) { $config.gameDirectory = $candidate; break }
    }
}
if (!$config.gameDirectory -or !(Test-Path -LiteralPath (Join-Path $config.gameDirectory $config.gameExecutable))) {
    throw 'GTA V Enhanced was not found. Rerun Setup.ps1 -GameDirectory "D:\path\Grand Theft Auto V Enhanced".'
}
if (!$config.steamExecutable -or !(Test-Path -LiteralPath $config.steamExecutable)) {
    throw 'Steam was not found. Set steamExecutable in config/local.json. This release supports the Steam edition.'
}
# Machine-local settings and secrets never enter Git.
$config | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$ProjectRoot/config/local.json" -Encoding UTF8
$tokenPath = Join-Path $ProjectRoot 'runtime/bridge-token'
if (!(Test-Path -LiteralPath $tokenPath)) {
    $bytes = New-Object byte[] 32
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($bytes) } finally { $random.Dispose() }
    [IO.File]::WriteAllText($tokenPath, [Convert]::ToBase64String($bytes))
}
if (!(Test-Path -LiteralPath "$ProjectRoot/runtime/model-profile.txt")) {
    [IO.File]::WriteAllText("$ProjectRoot/runtime/model-profile.txt", "default`n")
}
if (!(Test-Path -LiteralPath "$ProjectRoot/runtime/ui-overlay.json")) {
    [IO.File]::WriteAllText("$ProjectRoot/runtime/ui-overlay.json", '{"enabled":true,"width":720}')
}
if ($Stage -eq 'Configure') { Write-Output 'Local configuration saved.'; return }
if ($Stage -in @('All','Windows')) {
    if (!(Test-Path -LiteralPath "$ProjectRoot/.venv/Scripts/python.exe")) {
        if ($PythonExe) {
            Invoke-Checked $PythonExe @('-c','import sys, tkinter; assert sys.version_info[:2] == (3, 13), "Python 3.13 required"')
            Invoke-Checked $PythonExe @('-m','venv',"$ProjectRoot/.venv")
        } else {
            Invoke-Checked 'py.exe' @('-3.13','-c','import tkinter')
            Invoke-Checked 'py.exe' @('-3.13','-m','venv',"$ProjectRoot/.venv")
        }
    }
    Invoke-Checked "$ProjectRoot/.venv/Scripts/python.exe" @('-m','pip','install','-r',"$ProjectRoot/config/windows-requirements.txt")
    Invoke-Checked "$ProjectRoot/.venv/Scripts/python.exe" @('-c','import tkinter, numpy, cv2, windows_capture; print("Windows dependencies ready")')
}
if ($Stage -in @('All','Native')) {
    if (!(Test-Path -LiteralPath "$ProjectRoot/vendor/ScriptHookV_SDK/inc/main.h")) {
        throw 'Download the official Script Hook V SDK and extract inc/ and lib/ under vendor/ScriptHookV_SDK. See README.'
    }
    Invoke-Checked 'cmake.exe' @('-S',"$ProjectRoot/native",'-B',"$ProjectRoot/build/native",'-G','Visual Studio 17 2022','-A','x64')
    Invoke-Checked 'cmake.exe' @('--build',"$ProjectRoot/build/native",'--config','Release','--parallel',([string]$config.buildJobs))
    Invoke-Checked 'ctest.exe' @('--test-dir',"$ProjectRoot/build/native",'-C','Release','--output-on-failure')
}
if ($Stage -in @('All','Linux')) {
    Invoke-Checked 'wsl.exe' @('--status')
    $names = @((& wsl.exe --list --quiet) -replace "`0", '' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($LASTEXITCODE -ne 0) { throw 'WSL is not ready. See README prerequisites.' }
    if ($config.wslDistribution -notin $names) {
        if (!$RootfsPath) {
            $RootfsPath = Join-Path $ProjectRoot 'downloads/ubuntu-24.04.5-wsl-amd64.wsl'
            if (!(Test-Path -LiteralPath $RootfsPath)) {
                Invoke-WebRequest -UseBasicParsing -Uri $config.ubuntu.url -OutFile "$RootfsPath.download"
                if ((Get-FileHash -LiteralPath "$RootfsPath.download" -Algorithm SHA256).Hash -ne $config.ubuntu.sha256) { throw 'Ubuntu download hash mismatch.' }
                Move-Item -LiteralPath "$RootfsPath.download" -Destination $RootfsPath
            }
        }
        if ((Get-FileHash -LiteralPath $RootfsPath -Algorithm SHA256).Hash -ne $config.ubuntu.sha256) { throw 'Ubuntu image hash mismatch.' }
        Invoke-Checked 'wsl.exe' @('--import',$config.wslDistribution,"$ProjectRoot/runtime/wsl",$RootfsPath,'--version','2')
        $linuxRoot = Get-LinuxProjectRoot $config
        Invoke-Checked 'wsl.exe' @('-d',$config.wslDistribution,'-u','root','--exec','bash',"$linuxRoot/scripts/claim-distribution.sh")
    }
    $linuxRoot = Get-LinuxProjectRoot $config
    Assert-ProjectDistribution $config $linuxRoot
    $manager = & wsl.exe -d $config.wslDistribution -u root --exec pgrep -f '^python manager.py'
    if ($LASTEXITCODE -eq 0) { throw 'Stop this clone before updating its Linux build.' }
    Invoke-Checked 'wsl.exe' @('-d',$config.wslDistribution,'-u','root','--exec','bash',"$linuxRoot/scripts/bootstrap-linux.sh")
    Invoke-Checked 'wsl.exe' @('-d',$config.wslDistribution,'-u',$config.linuxUser,'--exec','bash',"$linuxRoot/scripts/build-frogpilot.sh",([string]$config.buildJobs))
    @{sourceCommit=$config.frogpilot.commit;model='macrostiff';completedUtc=[DateTime]::UtcNow.ToString('o')} |
        ConvertTo-Json | Set-Content -LiteralPath "$ProjectRoot/runtime/linux-ready.json" -Encoding UTF8
}
Write-Output 'Setup stage completed. With GTA closed, run scripts/Install-GameBridge.ps1, then Start-NMKAi.cmd.'
