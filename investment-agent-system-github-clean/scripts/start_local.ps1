. (Join-Path $PSScriptRoot "common.ps1")

$ports = Get-DefaultPorts
$projectRoot = Get-ProjectRoot

function Start-ManagedProcess {
    param(
        [string]$WorkingDirectory,
        [string[]]$Arguments,
        [string]$StdoutPath,
        [string]$StderrPath
    )

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = "python"
    $psi.Arguments = (($Arguments | ForEach-Object {
        if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
    }) -join ' ')
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    $stdoutWriter = [System.IO.StreamWriter]::new($StdoutPath, $false)
    $stderrWriter = [System.IO.StreamWriter]::new($StderrPath, $false)
    $process.add_OutputDataReceived({
        param($sender, $eventArgs)
        if ($null -ne $eventArgs.Data) {
            $stdoutWriter.WriteLine($eventArgs.Data)
            $stdoutWriter.Flush()
        }
    })
    $process.add_ErrorDataReceived({
        param($sender, $eventArgs)
        if ($null -ne $eventArgs.Data) {
            $stderrWriter.WriteLine($eventArgs.Data)
            $stderrWriter.Flush()
        }
    })
    $process.EnableRaisingEvents = $true
    $process.add_Exited({
        $stdoutWriter.Dispose()
        $stderrWriter.Dispose()
    })
    [void]$process.Start()
    $process.BeginOutputReadLine()
    $process.BeginErrorReadLine()

    return $process
}

function Ensure-Service {
    param(
        [string]$Name,
        [int]$Port,
        [string]$HealthUrl,
        [string]$WorkingDirectory,
        [string[]]$Arguments
    )

    $existingPid = Get-PortPid -Port $Port
    if ($existingPid) {
        try {
            $response = Wait-ForHttp -Url $HealthUrl -TimeoutSeconds 3
            Write-Host "$Name already running on port $Port (PID $existingPid)." -ForegroundColor Green
            Write-Pid -Name $Name -ProcessId $existingPid
            return
        } catch {
            Write-Host "$Name port $Port is occupied by a stale process. Restarting..." -ForegroundColor Yellow
            Stop-ManagedProcess -Name $Name -Port $Port
        }
    }

    $stdout = Get-LogFile -Name "${Name}_stdout"
    $stderr = Get-LogFile -Name "${Name}_stderr"
    if (Test-Path $stdout) {
        try { Remove-Item -Force $stdout } catch {}
    }
    if (Test-Path $stderr) {
        try { Remove-Item -Force $stderr } catch {}
    }

    $process = Start-ManagedProcess `
        -WorkingDirectory $WorkingDirectory `
        -Arguments $Arguments `
        -StdoutPath $stdout `
        -StderrPath $stderr

    Write-Pid -Name $Name -ProcessId $process.Id
    Wait-ForHttp -Url $HealthUrl -TimeoutSeconds 20 | Out-Null
    Write-Host "$Name started on port $Port (PID $($process.Id))." -ForegroundColor Green
}

Ensure-Service `
    -Name "backend" `
    -Port $ports.Backend `
    -HealthUrl "http://127.0.0.1:$($ports.Backend)/health" `
    -WorkingDirectory $projectRoot `
    -Arguments @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$($ports.Backend)")

Write-Host ""
Write-Host "Backend : http://127.0.0.1:$($ports.Backend)" -ForegroundColor Cyan
Write-Host "Frontend: http://127.0.0.1:$($ports.Backend)/ui" -ForegroundColor Cyan
