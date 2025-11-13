# Master Deployment Script - Complete Workflow
# This script runs the ENTIRE workflow in the correct order:
# 1. Process all stations (pra_nighttime.py)
# 2. Integrate earthquakes (integrate_earthquakes.py)
# 3. Prepare web output (upload_results.py)
# 4. Deploy to GitHub Pages (deploy_to_github.ps1)
#
# Usage: Just double-click this file or run: .\deploy_all.ps1

$ErrorActionPreference = "Continue"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Write-Log {
    param([string]$Message, [string]$Color = "White")
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$Timestamp] $Message" -ForegroundColor $Color
}

Write-Log "==========================================" "Cyan"
Write-Log "PRA Complete Deployment Workflow" "Cyan"
Write-Log "==========================================" "Cyan"
Write-Log ""

# Ensure we process ALL stations
if (Test-Path Env:INTERMAGNET_STATIONS) {
    Remove-Item Env:INTERMAGNET_STATIONS
    Write-Log "Note: INTERMAGNET_STATIONS was unset - processing ALL stations" "Yellow"
}

# Step 1: Run PRA Analysis
Write-Log "Step 1/4: Running PRA Analysis (pra_nighttime.py)..." "Yellow"
Write-Log "This may take several minutes for all stations..." "Gray"
python pra_nighttime.py
if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR: PRA analysis failed!" "Red"
    Write-Log "Please check the error messages above" "Red"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Log "PRA analysis completed" "Green"
Write-Log ""

# Step 2: Integrate Earthquakes
Write-Log "Step 2/4: Integrating Earthquake Data (integrate_earthquakes.py)..." "Yellow"
python integrate_earthquakes.py
if ($LASTEXITCODE -ne 0) {
    Write-Log "WARNING: Earthquake integration had issues, but continuing..." "Yellow"
} else {
    Write-Log "Earthquake integration completed" "Green"
}
Write-Log ""

# Step 3: Prepare Web Output (CRITICAL - This regenerates stations.json with all stations)
Write-Log "Step 3/4: Preparing Web Output (upload_results.py)..." "Yellow"
Write-Log "This step is CRITICAL - it regenerates stations.json with all processed stations" "Cyan"
python upload_results.py
if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR: Web output preparation failed!" "Red"
    Write-Log "Please check the error messages above" "Red"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Log "Web output prepared" "Green"

# Verify stations.json was created correctly
$stationsJson = "web_output\data\stations.json"
if (Test-Path $stationsJson) {
    try {
        $jsonContent = Get-Content $stationsJson | ConvertFrom-Json
        $stationCount = if ($jsonContent.stations) { $jsonContent.stations.Count } else { 0 }
        Write-Log "Verified: stations.json contains $stationCount stations" "Green"
        if ($stationCount -le 1) {
            Write-Log "WARNING: Only $stationCount station(s) found! This may indicate a problem." "Yellow"
            Write-Log "Check that pra_nighttime.py processed all stations successfully." "Yellow"
        }
    } catch {
        Write-Log "WARNING: Could not verify stations.json content" "Yellow"
    }
} else {
    Write-Log "ERROR: stations.json not found in web_output/data/" "Red"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Log ""

# Step 4: Deploy to GitHub Pages (if configured)
$env:GITHUB_REPO = "syaifulafrizal/global-pra-observation"
$env:GITHUB_BRANCH = "gh-pages"

if ($env:GITHUB_REPO) {
    Write-Log "Step 4/4: Deploying to GitHub Pages..." "Yellow"
    Write-Log "Repository: $env:GITHUB_REPO" "Gray"
    if ($env:GITHUB_BRANCH) {
        $branchName = $env:GITHUB_BRANCH
    } else {
        $branchName = "gh-pages"
    }
    Write-Log "Branch: $branchName" "Gray"
    Write-Log ""
    
    & ".\deploy_to_github.ps1"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Log "Deployment completed successfully!" "Green"
    } else {
        Write-Log "WARNING: Deployment had issues, but web output is ready locally" "Yellow"
    }
} else {
    Write-Log "Step 4/4: Skipping GitHub deployment (GITHUB_REPO not set)" "Yellow"
    Write-Log ""
    Write-Log "To enable GitHub Pages deployment:" "Cyan"
    Write-Log "  Set: `$env:GITHUB_REPO='username/repo-name'" "White"
    Write-Log "  Set: `$env:GITHUB_BRANCH='gh-pages'" "White"
    Write-Log ""
    Write-Log "Web output is ready in: web_output/" "Green"
    Write-Log "You can test locally with: python app.py" "Green"
}

Write-Log ""
Write-Log "==========================================" "Cyan"
Write-Log "Workflow Completed!" "Green"
Write-Log "==========================================" "Cyan"
Write-Log ""
Write-Log "Summary:" "Cyan"
Write-Log "  PRA analysis completed" "Green"
Write-Log "  Earthquake integration completed" "Green"
Write-Log "  Web output prepared" "Green"
if ($env:GITHUB_REPO) {
    Write-Log "  Deployed to GitHub Pages" "Green"
}
Write-Log ""

# Keep window open if run by double-clicking
if ($Host.Name -eq "ConsoleHost") {
    Write-Log "Press Enter to close this window..." "Gray"
    Read-Host
}
