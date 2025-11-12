# Keep Flask Server Running
# Monitors Flask server and restarts if it crashes
# Run this script to ensure Flask stays online

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$FlaskPort = 5000
$FlaskScript = "app.py"
$CheckInterval = 60  # Check every 60 seconds

function Test-FlaskRunning {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$FlaskPort" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Start-FlaskServer {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting Flask server..." -ForegroundColor Green
    $Process = Start-Process python -ArgumentList $FlaskScript -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 5  # Wait for server to start
    return $Process
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Flask Server Monitor" -ForegroundColor Cyan
Write-Host "Monitoring: http://localhost:$FlaskPort" -ForegroundColor Cyan
Write-Host "Check interval: $CheckInterval seconds" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Start Flask server initially
$FlaskProcess = Start-FlaskServer

# Monitor loop
while ($true) {
    if (-not (Test-FlaskRunning)) {
        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Flask server is down! Restarting..." -ForegroundColor Red
        
        # Kill any existing Python processes on port 5000
        $ExistingProcesses = Get-NetTCPConnection -LocalPort $FlaskPort -ErrorAction SilentlyContinue | 
            Select-Object -ExpandProperty OwningProcess -Unique
        if ($ExistingProcesses) {
            foreach ($pid in $ExistingProcesses) {
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            }
        }
        
        # Restart Flask
        $FlaskProcess = Start-FlaskServer
        
        if (Test-FlaskRunning) {
            Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Flask server restarted successfully" -ForegroundColor Green
        } else {
            Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Failed to restart Flask server" -ForegroundColor Red
        }
    } else {
        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Flask server is running OK" -ForegroundColor Gray
    }
    
    Start-Sleep -Seconds $CheckInterval
}

