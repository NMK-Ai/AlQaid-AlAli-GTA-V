# Uses fake files under build/, never the installed game or a real WSL distribution.
$ErrorActionPreference='Stop'
$repository=Split-Path -Parent $PSScriptRoot
$fixture=Join-Path $repository ('build/install-test-'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path "$fixture/clone with spaces/scripts","$fixture/clone with spaces/config","$fixture/game with spaces"
$clone=Join-Path $fixture 'clone with spaces'
$game=Join-Path $fixture 'game with spaces'
foreach ($name in @('Project.ps1','Setup.ps1','Install-GameBridge.ps1','Uninstall-GameBridge.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination "$clone/scripts/$name"
}
Copy-Item -LiteralPath "$repository/config/project.json" -Destination "$clone/config/project.json"
Copy-Item -LiteralPath "$repository/config/steering.ini" -Destination "$clone/config/steering.ini"
[IO.File]::WriteAllText("$game/GTA5_Enhanced.exe",'fake executable for installer test')
[IO.File]::WriteAllText("$fixture/steam.exe",'fake Steam for configuration test')
@{gameDirectory=$game;steamExecutable="$fixture/steam.exe"} | ConvertTo-Json | Set-Content "$clone/config/local.json"
& "$clone/scripts/Setup.ps1" -Stage Configure
# Real child argv parsing, including spaces, quotes and trailing backslashes.
. "$clone/scripts/Project.ps1"
$argumentsPath=Join-Path $fixture 'argv.json'
$python=(Get-Command python.exe).Source
Invoke-Checked $python @('-c','import json,sys; json.dump(sys.argv[2:],open(sys.argv[1],"w"))',$argumentsPath,'space in path','embedded"quote','trailing\')
$observed=Get-Content -LiteralPath $argumentsPath -Raw | ConvertFrom-Json
if ($observed.Count -ne 3 -or $observed[0] -ne 'space in path' -or $observed[1] -ne 'embedded"quote' -or $observed[2] -ne 'trailing\') { throw 'Native argument quoting failed' }
$token=[IO.File]::ReadAllText("$clone/runtime/bridge-token")
& "$clone/scripts/Setup.ps1" -Stage Configure
if ($token -ne [IO.File]::ReadAllText("$clone/runtime/bridge-token") -or [Convert]::FromBase64String($token).Length -ne 32) { throw 'Token generation/preservation failed' }
$null=New-Item -ItemType Directory -Force -Path "$clone/vendor/ScriptHookV_runtime/bin","$clone/build/native/Release"
foreach ($name in @('ScriptHookV.dll','dinput8.dll','xinput1_4.dll')) { [IO.File]::WriteAllText("$clone/vendor/ScriptHookV_runtime/bin/$name","test $name") }
[IO.File]::WriteAllText("$clone/build/native/Release/OpenPilotGTA.asi",'adapter v1')
Copy-Item -LiteralPath "$clone/vendor/ScriptHookV_runtime/bin/dinput8.dll" -Destination "$game/dinput8.dll"
# Shadow process discovery only in the fixture so tests can run while a real game is open.
function Get-Process { param($Name) return @() }
& "$clone/scripts/Install-GameBridge.ps1" -WhatIf
if (Test-Path -LiteralPath "$game/OpenPilotGTA.asi") { throw 'WhatIf changed game files' }
& "$clone/scripts/Install-GameBridge.ps1"
$installed=Get-Content "$clone/runtime/game-install.json" -Raw | ConvertFrom-Json
if (($installed.files | Where-Object name -eq 'dinput8.dll').owned) { throw 'Existing identical loader was claimed' }
& "$clone/scripts/Install-GameBridge.ps1"
[IO.File]::WriteAllText("$clone/build/native/Release/OpenPilotGTA.asi",'adapter v2')
& "$clone/scripts/Install-GameBridge.ps1"
if ([IO.File]::ReadAllText("$game/OpenPilotGTA.asi") -ne 'adapter v2') { throw 'Owned upgrade failed' }
[IO.File]::WriteAllText("$game/ScriptHookV.dll",'another mod changed this')
$refused=$false
try { & "$clone/scripts/Uninstall-GameBridge.ps1" } catch { $refused=$true }
if (!$refused -or !(Test-Path "$game/OpenPilotGTA.asi")) { throw 'Changed file did not stop uninstall before removal' }
Copy-Item -LiteralPath "$clone/vendor/ScriptHookV_runtime/bin/ScriptHookV.dll" -Destination "$game/ScriptHookV.dll"
& "$clone/scripts/Uninstall-GameBridge.ps1"
if (!(Test-Path "$game/dinput8.dll") -or (Test-Path "$game/OpenPilotGTA.asi")) { throw 'Uninstall ownership failed' }
[IO.File]::WriteAllText("$game/ScriptHookV.dll",'unrelated loader')
$refused=$false
try { & "$clone/scripts/Install-GameBridge.ps1" } catch { $refused=$true }
if (!$refused -or (Test-Path "$game/OpenPilotGTA.asi")) { throw 'Conflicting loader did not stop preflight' }
Write-Output 'PASS: configuration, token reuse, paths with spaces, WhatIf, install, repeat install, upgrade, changed-file preservation, ownership and conflicting-mod preflight.'
