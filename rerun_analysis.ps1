# PowerShell script to rerun analysis for all stations
# This deletes existing JSON results to force reprocessing

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "PRA Analysis Rerun Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will delete existing analysis results and rerun for all stations." -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "Continue? (Y/N)"
if ($confirm -ne 'Y' -and $confirm -ne 'y') {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Deleting existing analysis results..." -ForegroundColor Yellow

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
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Starting analysis with FORCE_RERUN enabled..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$env:FORCE_RERUN = "1"

# Try to use Anaconda Python first, fallback to system python
$pythonExe = $null
if (Test-Path "C:\Users\SYAIFUL\anaconda3\python.exe") {
    $pythonExe = "C:\Users\SYAIFUL\anaconda3\python.exe"
    Write-Host "Using Anaconda Python: $pythonExe" -ForegroundColor Gray
} else {
    $pythonExe = "python"
    Write-Host "Using system Python" -ForegroundColor Gray
}

& $pythonExe pra_nighttime.py

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Analysis complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

if ($Host.Name -eq "ConsoleHost") {
    Read-Host "Press Enter to close"
}

