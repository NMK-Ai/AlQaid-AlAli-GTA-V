. "$PSScriptRoot/Project.ps1"
Initialize-ProjectDirectories
if (!(Find-ProjectPythonProcess 'ui_overlay.py')) {
    $null=Start-ProjectProcess "$ProjectRoot/.venv/Scripts/pythonw.exe" @("$ProjectRoot/bridge/ui_overlay.py")
}
