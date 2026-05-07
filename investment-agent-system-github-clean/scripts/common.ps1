Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-RuntimeDir {
    $runtimeDir = Join-Path (Get-ProjectRoot) ".runtime"
    if (-not (Test-Path $runtimeDir)) {
        New-Item -ItemType Directory -Path $runtimeDir | Out-Null
    }
    return $runtimeDir
}

function Get-DefaultPorts {
    return @{
        Backend = 8023
    }
}

function Get-PidFile {
    param([string]$Name)
    return (Join-Path (Get-RuntimeDir) "$Name.pid")
}

function Get-LogFile {
    param([string]$Name)
    return (Join-Path (Get-RuntimeDir) "$Name.log")
}

function Read-Pid {
    param([string]$Name)
    $path = Get-PidFile -Name $Name
    if (-not (Test-Path $path)) {
        return $null
    }
    $content = (Get-Content $path -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $content) {
        return $null
    }
    return [int]$content
}

function Write-Pid {
    param([string]$Name, [int]$ProcessId)
    Set-Content -Path (Get-PidFile -Name $Name) -Value $ProcessId -NoNewline
}

function Remove-PidFile {
    param([string]$Name)
    $path = Get-PidFile -Name $Name
    if (Test-Path $path) {
        Remove-Item -Force $path
    }
}

function Test-ProcessAlive {
    param([int]$ProcessId)
    if (-not $ProcessId) {
        return $false
    }
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Get-PortPid {
    param([int]$Port)
    $lines = netstat -ano | Select-String (":$Port\s")
    foreach ($line in $lines) {
        $text = ($line.ToString() -replace "\s+", " ").Trim()
        if ($text -match "LISTENING\s+(\d+)$") {
            return [int]$matches[1]
        }
    }
    return $null
}

function Wait-ForHttp {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 20
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
            return $response
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Timed out waiting for $Url"
}

function Stop-ManagedProcess {
    param(
        [string]$Name,
        [int]$Port
    )
    $managedProcessId = Read-Pid -Name $Name
    if ($managedProcessId -and (Test-ProcessAlive -ProcessId $managedProcessId)) {
        Stop-Process -Id $managedProcessId -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
    Remove-PidFile -Name $Name

    $portPid = Get-PortPid -Port $Port
    if ($portPid) {
        Stop-Process -Id $portPid -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
}
