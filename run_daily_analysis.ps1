# Daily PRA Analysis Workflow
# Runs: pra_nighttime.py -> integrate_earthquakes.py -> upload_results.py
# Designed to run via Windows Task Scheduler at 12:00 PM GMT+8
#
# NOTE: This script processes ALL stations from stations.json automatically.
# To process specific stations only, set INTERMAGNET_STATIONS environment variable
# before running (e.g., $env:INTERMAGNET_STATIONS="KAK,HER")

$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Ensure we process ALL stations (unset INTERMAGNET_STATIONS if it exists)
# This ensures the script processes all stations from stations.json
if (Test-Path Env:INTERMAGNET_STATIONS) {
    Remove-Item Env:INTERMAGNET_STATIONS
    Write-Host "Note: INTERMAGNET_STATIONS was unset - processing ALL stations" -ForegroundColor Yellow
}

# Log file
$LogDir = "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$LogFile = Join-Path $LogDir "daily_analysis_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

function Write-Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] $Message"
    Write-Host $LogMessage
    Add-Content -Path $LogFile -Value $LogMessage
}

Write-Log "=========================================="
Write-Log "Starting Daily PRA Analysis Workflow"
Write-Log "=========================================="

try {
    # Step 1: Run main analysis
    Write-Log "Step 1: Running PRA analysis (pra_nighttime.py)..."
    python pra_nighttime.py 2>&1 | Tee-Object -FilePath $LogFile -Append
    if ($LASTEXITCODE -ne 0) {
        throw "PRA analysis failed with exit code $LASTEXITCODE"
    }
    Write-Log "PRA analysis completed successfully"
    
    # Step 2: Integrate earthquakes
    Write-Log "Step 2: Integrating earthquake data (integrate_earthquakes.py)..."
    python integrate_earthquakes.py 2>&1 | Tee-Object -FilePath $LogFile -Append
    if ($LASTEXITCODE -ne 0) {
        Write-Log "WARNING: Earthquake integration failed, continuing..."
    } else {
        Write-Log "Earthquake integration completed"
    }
    
    # Step 3: Prepare web files
    Write-Log "Step 3: Preparing web files (upload_results.py)..."
    python upload_results.py 2>&1 | Tee-Object -FilePath $LogFile -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Web file preparation failed with exit code $LASTEXITCODE"
    }
    Write-Log "Web files prepared successfully"
    
    # Step 4: Deploy to GitHub Pages (optional)
    if ($env:GITHUB_REPO) {
        Write-Log "Step 4: Deploying to GitHub Pages..."
        powershell.exe -ExecutionPolicy Bypass -File "deploy_to_github.ps1" 2>&1 | Tee-Object -FilePath $LogFile -Append
        if ($LASTEXITCODE -ne 0) {
            Write-Log "WARNING: GitHub deployment failed, but analysis completed"
        } else {
            Write-Log "GitHub Pages deployment completed"
        }
    } else {
        Write-Log "Step 4: Skipping GitHub deployment (GITHUB_REPO not set)"
    }
    
    Write-Log "=========================================="
    Write-Log "Daily workflow completed successfully!"
    Write-Log "=========================================="
    
    exit 0
    
} catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    Write-Log "Stack trace: $($_.ScriptStackTrace)"
    exit 1
}

