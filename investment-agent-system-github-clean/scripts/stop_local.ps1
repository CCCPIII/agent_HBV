. (Join-Path $PSScriptRoot "common.ps1")

$ports = Get-DefaultPorts

Stop-ManagedProcess -Name "backend" -Port $ports.Backend

Write-Host "Stopped local backend if it was running." -ForegroundColor Yellow
