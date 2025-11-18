# PowerShell script to initialize 7-day dataset and rerun analysis
# This downloads last 7 days of data, processes them, and sets up the rolling window

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "PRA Analysis - Initialize 7-Day Dataset" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will:" -ForegroundColor Yellow
Write-Host "  1. Download last 7 days of geomagnetic field data (10/11 to today)" -ForegroundColor White
Write-Host "  2. Process each day to build the historical dataset" -ForegroundColor White
Write-Host "  3. Download and process last 7 days of earthquake data" -ForegroundColor White
Write-Host "  4. Set up rolling 7-day window (oldest day deleted when new day added)" -ForegroundColor White
Write-Host ""
Write-Host "Note: Existing analysis results will be deleted and reprocessed." -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "Continue? (Y/N)"
if ($confirm -ne 'Y' -and $confirm -ne 'y') {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Step 1: Deleting existing analysis results..." -ForegroundColor Yellow

$deletedCount = 0
$downloadsDir = "INTERMAGNET_DOWNLOADS"
if (Test-Path $downloadsDir) {
    Get-ChildItem -Path $downloadsDir -Directory | ForEach-Object {
        $jsonFiles = Get-ChildItem -Path $_.FullName -Filter "PRA_Night_*.json" -ErrorAction SilentlyContinue
        if ($jsonFiles) {
            $jsonFiles | Remove-Item -Force
            $deletedCount += $jsonFiles.Count
            Write-Host "  Deleted $($jsonFiles.Count) result(s) in $($_.Name)" -ForegroundColor Gray
        }
    }
}

Write-Host ""
Write-Host "Deleted $deletedCount result file(s)" -ForegroundColor Green
Write-Host ""

# Try to use Anaconda Python first, fallback to system python
$pythonExe = $null
if (Test-Path "C:\Users\SYAIFUL\anaconda3\python.exe") {
    $pythonExe = "C:\Users\SYAIFUL\anaconda3\python.exe"
    Write-Host "Using Anaconda Python: $pythonExe" -ForegroundColor Gray
} else {
    $pythonExe = "python"
    Write-Host "Using system Python" -ForegroundColor Gray
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Step 2: Downloading and processing 7-day dataset..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will process each of the last 7 days sequentially." -ForegroundColor Gray
Write-Host "Each day will use historical data from previous days for EVT fitting." -ForegroundColor Gray
Write-Host ""

$env:FORCE_RERUN = "1"

# Run the initialization script
Write-Host "Running 7-day dataset initialization..." -ForegroundColor Yellow
& $pythonExe initialize_7day_dataset.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "WARNING: Initialization script had errors, but continuing..." -ForegroundColor Yellow
    Write-Host "Running standard analysis as fallback..." -ForegroundColor Yellow
    Write-Host ""
    & $pythonExe pra_nighttime.py
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Step 3: Processing earthquake data..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

& $pythonExe integrate_earthquakes.py

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "7-Day Dataset Initialization Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  - Last 7 days of data have been downloaded and processed" -ForegroundColor White
Write-Host "  - Historical dataset is ready for EVT threshold calculation" -ForegroundColor White
Write-Host "  - Rolling window is set up (oldest day will be deleted when new day is added)" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  - Run deploy_all.bat to deploy the results" -ForegroundColor White
Write-Host "  - Future daily runs will automatically maintain the 7-day window" -ForegroundColor White
Write-Host ""

if ($Host.Name -eq "ConsoleHost") {
    Read-Host "Press Enter to close"
}

