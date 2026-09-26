. "$PSScriptRoot/Project.ps1"
Initialize-ProjectDirectories
if (!(Find-ProjectPythonProcess 'gta_road_context.py')) {
    $null=Start-ProjectProcess "$ProjectRoot/.venv/Scripts/pythonw.exe" @("$ProjectRoot/bridge/gta_road_context.py")
}
