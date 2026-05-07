. (Join-Path $PSScriptRoot "common.ps1")

$ports = Get-DefaultPorts

foreach ($item in @(
    @{ Name = "backend"; Port = $ports.Backend; Url = "http://127.0.0.1:$($ports.Backend)/health" },
    @{ Name = "frontend"; Port = $ports.Backend; Url = "http://127.0.0.1:$($ports.Backend)/ui" }
)) {
    $processId = Get-PortPid -Port $item.Port
    if (-not $processId) {
        Write-Host "$($item.Name): stopped" -ForegroundColor Red
        continue
    }

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $item.Url -TimeoutSec 3
        Write-Host "$($item.Name): running on port $($item.Port) (PID $processId, HTTP $($response.StatusCode))" -ForegroundColor Green
    } catch {
        Write-Host "$($item.Name): process listening on port $($item.Port) (PID $processId) but HTTP check failed" -ForegroundColor Yellow
    }
}
