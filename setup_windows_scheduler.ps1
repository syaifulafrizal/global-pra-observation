# Setup Windows Task Scheduler for Daily PRA Analysis
# Run this script ONCE to set up automatic daily execution at 12:00 PM GMT+8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = "PRA_Daily_Analysis"
$ScriptPath = Join-Path $ScriptDir "run_daily_analysis.ps1"

Write-Host "Setting up Windows Task Scheduler for PRA Daily Analysis..." -ForegroundColor Cyan
Write-Host ""

# Check if task already exists
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($ExistingTask) {
    Write-Host "Task '$TaskName' already exists. Updating..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create action (run PowerShell script)
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$ScriptPath`""

# Create trigger: Daily at 12:00 PM (GMT+8 = UTC+8)
# Windows uses local time, so 12:00 PM GMT+8 = 12:00 PM local time if server is in GMT+8
$Trigger = New-ScheduledTaskTrigger -Daily -At "12:00PM"

# Set timezone to Singapore (GMT+8)
$Trigger.StartBoundary = (Get-Date -Year (Get-Date).Year -Month (Get-Date).Month -Day (Get-Date).Day -Hour 12 -Minute 0 -Second 0).ToString("yyyy-MM-ddTHH:mm:ss")
$Trigger.Enabled = $true

# Create settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# Create principal (run as current user, highest privileges)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

# Register the task
try {
    Register-ScheduledTask -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Daily PRA Nighttime Analysis - Runs at 12:00 PM GMT+8" | Out-Null
    
    Write-Host "SUCCESS: Task '$TaskName' has been created!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Task Details:" -ForegroundColor Cyan
    Write-Host "  Name: $TaskName"
    Write-Host "  Schedule: Daily at 12:00 PM (GMT+8)"
    Write-Host "  Script: $ScriptPath"
    Write-Host ""
    Write-Host "To verify, run: Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
    Write-Host "To test manually, run: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
    Write-Host "To view logs, check: $ScriptDir\logs\" -ForegroundColor Yellow
    
} catch {
    Write-Host "ERROR: Failed to create scheduled task" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "You may need to run PowerShell as Administrator" -ForegroundColor Yellow
    exit 1
}

