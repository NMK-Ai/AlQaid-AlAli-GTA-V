[CmdletBinding(SupportsShouldProcess=$true)]
param()
. "$PSScriptRoot/Project.ps1"
$config = Get-ProjectConfig
Initialize-ProjectDirectories
if (Get-Process GTA5_Enhanced -ErrorAction SilentlyContinue) { throw 'Close GTA before installing its adapter.' }
if (!$config.gameDirectory -or !(Test-Path -LiteralPath (Join-Path $config.gameDirectory $config.gameExecutable))) { throw 'Run Setup first.' }
$manifestPath = Join-Path $ProjectRoot 'runtime/game-install.json'
$previous = @{}
if (Test-Path -LiteralPath $manifestPath) {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.gameDirectory -ne $config.gameDirectory) { throw 'Installation belongs to another game directory; uninstall it first.' }
    foreach ($entry in $manifest.files) { $previous[$entry.name] = $entry }
}
$specs = @(
    @{source='vendor/ScriptHookV_runtime/bin/ScriptHookV.dll';name='ScriptHookV.dll'},
    @{source='vendor/ScriptHookV_runtime/bin/dinput8.dll';name='dinput8.dll'},
    @{source='vendor/ScriptHookV_runtime/bin/xinput1_4.dll';name='xinput1_4.dll'},
    @{source='build/native/Release/OpenPilotGTA.asi';name='OpenPilotGTA.asi'},
    @{source='config/steering.ini';name='OpenPilotGTA.ini'}
)
$plan = @()
foreach ($spec in $specs) {
    $source = Join-Path $ProjectRoot $spec.source
    $target = Join-Path $config.gameDirectory $spec.name
    if (!(Test-Path -LiteralPath $source)) { throw "Missing $source. Obtain a matching official Enhanced loader/SDK; see README." }
    $hash = (Get-FileHash -LiteralPath $source).Hash
    $exists = Test-Path -LiteralPath $target
    $owned = $previous.ContainsKey($spec.name) -and $previous[$spec.name].owned
    if ($exists) {
        $existingHash = (Get-FileHash -LiteralPath $target).Hash
        if ($owned -and $existingHash -ne $previous[$spec.name].sha256) { throw "Installed file changed; preserve for review: $target" }
        if (!$owned -and $existingHash -ne $hash) { throw "Existing mod/loader differs; left untouched: $target" }
    }
    $plan += [pscustomobject]@{name=$spec.name;source=$source;target=$target;sha256=$hash;owned=(!$exists -or $owned);copy=(!$exists -or ($owned -and $existingHash -ne $hash))}
}
if (!$PSCmdlet.ShouldProcess($config.gameDirectory,'Install manifest-tracked Story Mode adapter and loader')) { return }
$backup = Join-Path $ProjectRoot ('runtime/install-backups/'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
$null = New-Item -ItemType Directory -Path $backup
if (Test-Path -LiteralPath $manifestPath) { Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $backup 'manifest.json') }
$changed = @()
try {
    foreach ($entry in $plan) {
        if (!$entry.copy) { continue }
        if (Test-Path -LiteralPath $entry.target) { Copy-Item -LiteralPath $entry.target -Destination (Join-Path $backup $entry.name) }
        $changed += $entry
        Copy-Item -LiteralPath $entry.source -Destination $entry.target
        if ((Get-FileHash -LiteralPath $entry.target).Hash -ne $entry.sha256) { throw 'Installed hash mismatch.' }
    }
    @{gameDirectory=$config.gameDirectory;files=@($plan | Select-Object name,sha256,owned)} |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
} catch {
    foreach ($entry in $changed) {
        $saved = Join-Path $backup $entry.name
        if (Test-Path -LiteralPath $saved) { Copy-Item -LiteralPath $saved -Destination $entry.target }
        elseif (Test-Path -LiteralPath $entry.target) { Remove-Item -LiteralPath $entry.target }
    }
    throw
}
Write-Output 'Adapter installed. Launch Story Mode with Start-NMKAi.cmd.'
