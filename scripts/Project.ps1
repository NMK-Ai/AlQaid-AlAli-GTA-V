# Shared configuration and process helpers. Compatible with Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
# WSL emits UTF-8; decode its output correctly so paths with non-ASCII user
# names (e.g. Arabic) survive the PowerShell round-trip instead of arriving
# mojibake on the Linux side.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ProjectRoot = Split-Path -Parent $PSScriptRoot
function Get-ProjectConfig {
    $values = @{}
    foreach ($file in @('config/project.json', 'config/local.json')) {
        $path = Join-Path $ProjectRoot $file
        if (Test-Path -LiteralPath $path) {
            $data = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
            foreach ($property in $data.PSObject.Properties) { $values[$property.Name] = $property.Value }
        }
    }
    if ($values.wslDistribution -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$') { throw 'Invalid WSL distribution name.' }
    if ($values.linuxUser -ne 'frogpilot') { throw 'This release uses the dedicated frogpilot Linux user.' }
    if ([int]$values.buildJobs -lt 1 -or [int]$values.buildJobs -gt 64) { throw 'buildJobs must be 1..64.' }
    return [pscustomobject]$values
}
function Initialize-ProjectDirectories {
    foreach ($name in @('runtime','reports','downloads','vendor','build')) {
        $null = New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot $name)
    }
}
function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = ($Arguments | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $info.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    # Drain both streams concurrently and show progress during long builds.
    $process = [Diagnostics.Process]::Start($info)
    $stdout = $process.StandardOutput.ReadLineAsync()
    $stderr = $process.StandardError.ReadLineAsync()
    $outDone = $false; $errDone = $false
    while (!$outDone -or !$errDone) {
        if (!$outDone -and $stdout.IsCompleted) {
            if ($null -eq $stdout.Result) { $outDone=$true }
            else { Write-Host $stdout.Result; $stdout=$process.StandardOutput.ReadLineAsync() }
        }
        if (!$errDone -and $stderr.IsCompleted) {
            if ($null -eq $stderr.Result) { $errDone=$true }
            else { Write-Host $stderr.Result; $stderr=$process.StandardError.ReadLineAsync() }
        }
        if (!$outDone -or !$errDone) { Start-Sleep -Milliseconds 10 }
    }
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "$Executable failed (exit $($process.ExitCode))." }
}
function Get-LinuxProjectRoot {
    param($Config)
    $result = & wsl.exe -d $Config.wslDistribution -u root --exec wslpath -a -u $ProjectRoot
    if ($LASTEXITCODE -ne 0 -or !$result) { throw 'Cannot map the clone directory into WSL.' }
    return ($result | Out-String).Trim()
}
function Assert-ProjectDistribution {
    param($Config, [string]$LinuxRoot)
    $owner = & wsl.exe -d $Config.wslDistribution -u root --exec cat /etc/frogpilot-gta-project 2>$null
    if ($LASTEXITCODE -ne 0 -or ($owner | Out-String).Trim() -ne $LinuxRoot) {
        throw 'This WSL distribution is not owned by this clone. Use a different wslDistribution in config/local.json.'
    }
}
function ConvertTo-ProcessArgument {
    param([string]$Value)
    # Windows CommandLineToArgvW quoting, including spaces and trailing backslashes.
    if ($Value.Contains([char]0) -or $Value.Contains("`r") -or $Value.Contains("`n")) { throw 'Invalid process argument.' }
    # WSL parses its switches before handing the remaining command to Linux.
    # Do not unnecessarily quote switches or other simple arguments.
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    return '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}
function Start-ProjectProcess {
    param([string]$Executable, [string[]]$Arguments, [string]$LogName)
    $options = @{
        FilePath=$Executable; ArgumentList=(($Arguments | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' ')
        WorkingDirectory=$ProjectRoot; WindowStyle='Hidden'; PassThru=$true
    }
    if ($LogName) {
        $options.RedirectStandardOutput = Join-Path $ProjectRoot "reports/$LogName.log"
        $options.RedirectStandardError = Join-Path $ProjectRoot "reports/$LogName-error.log"
    }
    Start-Process @options
}
function Find-ProjectPythonProcess {
    param([string]$Script)
    $path = Join-Path $ProjectRoot "bridge/$Script"
    @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.Replace('/','\').Contains($path.Replace('/','\')) })
}
