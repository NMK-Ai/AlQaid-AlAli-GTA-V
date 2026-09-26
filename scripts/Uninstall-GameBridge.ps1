[CmdletBinding(SupportsShouldProcess=$true)]
param()
. "$PSScriptRoot/Project.ps1"
if (Get-Process GTA5_Enhanced -ErrorAction SilentlyContinue) { throw 'Close GTA first.' }
$config = Get-ProjectConfig
$path = Join-Path $ProjectRoot 'runtime/game-install.json'
$manifest = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
if ($manifest.gameDirectory -ne $config.gameDirectory) { throw 'Game directory mismatch.' }
foreach ($entry in $manifest.files) {
    if ($entry.name -notin @('ScriptHookV.dll','dinput8.dll','xinput1_4.dll','OpenPilotGTA.asi','OpenPilotGTA.ini')) { throw 'Invalid manifest entry.' }
    $target = Join-Path $config.gameDirectory $entry.name
    if ($entry.owned -and (Test-Path -LiteralPath $target) -and (Get-FileHash -LiteralPath $target).Hash -ne $entry.sha256) { throw "Changed file preserved: $target" }
}
if ($PSCmdlet.ShouldProcess($config.gameDirectory,'Remove only unchanged, project-owned installed files')) {
    foreach ($entry in $manifest.files) {
        $target = Join-Path $config.gameDirectory $entry.name
        if ($entry.owned -and (Test-Path -LiteralPath $target)) { Remove-Item -LiteralPath $target }
    }
    Remove-Item -LiteralPath $path
}
