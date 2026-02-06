# GEMPRA Deployment Automation Documentation

## Overview

The GEMPRA platform uses **Windows Task Scheduler** for automated daily data processing and deployment. All automation runs on a local Windows machine in the **GMT+8 timezone** (Malaysia/Singapore time).

---

## Automation Architecture

```
┌─────────────────────────────────────────────────────────────┐
│           Windows Task Scheduler (GMT+8)                     │
│                                                               │
│  Trigger: Daily at configured time (e.g., 6:00 AM)          │
│  Action: Execute PowerShell script                           │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│         PowerShell Automation Script                         │
│                                                               │
│  1. Navigate to project directory                            │
│  2. Run earthquake integration (Python)                      │
│  3. Run data processing (Python)                             │
│  4. Prepare web output files                                 │
│  5. Commit changes to Git                                    │
│  6. Push to GitHub                                           │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              GitHub Pages Deployment                         │
│                                                               │
│  - Automatic deployment from main branch                     │
│  - Static site hosting                                       │
│  - Global CDN distribution                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## PowerShell Automation Script

### Main Processing Script

**File**: `run_daily_processing.ps1`

```powershell
# GEMPRA Daily Processing Script
# Runs automated data processing and deployment
# Timezone: GMT+8 (Malaysia/Singapore)

# Configuration
$ProjectPath = "C:\Users\SYAIFUL\Downloads\pra-observation"
$LogFile = "C:\Users\SYAIFUL\Downloads\pra-observation\logs\processing_$(Get-Date -Format 'yyyyMMdd').log"

# Function to log messages
function Write-Log {
    param($Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp GMT+8] $Message"
    Write-Host $LogMessage
    Add-Content -Path $LogFile -Value $LogMessage
}

# Start processing
Write-Log "=== GEMPRA Daily Processing Started ==="

try {
    # Navigate to project directory
    Set-Location $ProjectPath
    Write-Log "Working directory: $ProjectPath"

    # Step 1: Integrate earthquake data
    Write-Log "Step 1: Integrating earthquake data..."
    python integrate_earthquakes.py
    if ($LASTEXITCODE -ne 0) {
        throw "Earthquake integration failed with exit code $LASTEXITCODE"
    }
    Write-Log "Earthquake integration completed successfully"

    # Step 2: Process and prepare web output
    Write-Log "Step 2: Processing data and preparing web output..."
    python upload_results.py
    if ($LASTEXITCODE -ne 0) {
        throw "Data processing failed with exit code $LASTEXITCODE"
    }
    Write-Log "Data processing completed successfully"

    # Step 3: Git operations
    Write-Log "Step 3: Committing changes to Git..."

    # Check if there are changes
    $GitStatus = git status --porcelain
    if ($GitStatus) {
        # Add web output files
        git add web_output/*

        # Create commit message with timestamp
        $CommitMessage = "Automated update: $(Get-Date -Format 'yyyy-MM-dd HH:mm') GMT+8"
        git commit -m $CommitMessage

        Write-Log "Changes committed: $CommitMessage"

        # Push to GitHub
        Write-Log "Pushing to GitHub..."
        git push origin main

        if ($LASTEXITCODE -ne 0) {
            throw "Git push failed with exit code $LASTEXITCODE"
        }

        Write-Log "Successfully pushed to GitHub"
    } else {
        Write-Log "No changes detected, skipping Git operations"
    }

    Write-Log "=== GEMPRA Daily Processing Completed Successfully ==="

} catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    Write-Log "=== GEMPRA Daily Processing Failed ==="
    exit 1
}
```

---

## Windows Task Scheduler Configuration

### Creating the Scheduled Task

#### Method 1: Using Task Scheduler GUI

1. **Open Task Scheduler**
   
   - Press `Windows + R`
   - Type `taskschd.msc`
   - Press Enter

2. **Create New Task**
   
   - Click "Create Task" (not "Create Basic Task")
   - Name: `GEMPRA Daily Processing`
   - Description: `Automated daily processing for GEMPRA earthquake monitoring platform`

3. **General Tab**
   
   - ☑ Run whether user is logged on or not
   - ☑ Run with highest privileges
   - Configure for: Windows 10/11

4. **Triggers Tab**
   
   - Click "New"
   - Begin the task: On a schedule
   - Settings: Daily
   - Start: [Choose time, e.g., 6:00 AM]
   - Recur every: 1 days
   - ☑ Enabled

5. **Actions Tab**
   
   - Click "New"
   - Action: Start a program
   - Program/script: `powershell.exe`
   - Add arguments: `-ExecutionPolicy Bypass -File "C:\Users\SYAIFUL\Downloads\pra-observation\run_daily_processing.ps1"`
   - Start in: `C:\Users\SYAIFUL\Downloads\pra-observation`

6. **Conditions Tab**
   
   - ☑ Start only if the computer is on AC power
   - ☐ Stop if the computer switches to battery power
   - ☑ Wake the computer to run this task

7. **Settings Tab**
   
   - ☑ Allow task to be run on demand
   - ☑ Run task as soon as possible after a scheduled start is missed
   - If the task fails, restart every: 10 minutes
   - Attempt to restart up to: 3 times

#### Method 2: Using PowerShell Command

```powershell
# Create scheduled task using PowerShell
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"C:\Users\SYAIFUL\Downloads\pra-observation\run_daily_processing.ps1`"" `
    -WorkingDirectory "C:\Users\SYAIFUL\Downloads\pra-observation"

$Trigger = New-ScheduledTaskTrigger -Daily -At "06:00AM"

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -WakeToRun `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 10)

$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U `
    -RunLevel Highest

Register-ScheduledTask -TaskName "GEMPRA Daily Processing" `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Automated daily processing for GEMPRA earthquake monitoring platform"
```

---

## Timezone Configuration

### GMT+8 Timezone Details

- **Timezone**: Malaysia/Singapore Time (MYT/SGT)
- **UTC Offset**: +8 hours
- **No Daylight Saving Time**: Consistent year-round

### Execution Time Examples

If scheduled for **6:00 AM GMT+8**:

- **UTC Time**: 10:00 PM (previous day)
- **GMT Time**: 10:00 PM (previous day)
- **EST (GMT-5)**: 5:00 PM (previous day)

---

## Logging and Monitoring

### Log Files

- **Location**: `C:\Users\SYAIFUL\Downloads\pra-observation\logs\`
- **Format**: `processing_YYYYMMDD.log`
- **Retention**: Manual cleanup (recommend keeping last 30 days)

### Log Content

Each log file contains:

- Timestamp (GMT+8)
- Processing steps
- Success/failure status
- Error messages (if any)

### Monitoring

Check logs regularly for:

- Processing failures
- Git push errors
- Python script errors
- Network connectivity issues

---

## Error Handling

### Automatic Retry

- Task Scheduler retries failed tasks up to 3 times
- 10-minute interval between retries

### Manual Intervention

If automated processing fails:

1. Check log file for error details
2. Verify internet connectivity
3. Ensure Python environment is accessible
4. Check GitHub credentials
5. Run script manually to debug:
   
   ```powershell
   cd C:\Users\SYAIFUL\Downloads\pra-observation
   .\run_daily_processing.ps1
   ```

---

## Maintenance

### Regular Checks

- **Weekly**: Review log files for errors
- **Monthly**: Verify scheduled task is running
- **Quarterly**: Update Python dependencies

### Updating the Script

1. Edit `run_daily_processing.ps1`
2. Test manually before next scheduled run
3. Monitor first automated execution

### Changing Schedule

1. Open Task Scheduler
2. Find "GEMPRA Daily Processing"
3. Right-click → Properties
4. Modify trigger time in "Triggers" tab

---

## Troubleshooting

### Task Not Running

**Check**:

- Task Scheduler service is running
- Computer is powered on at scheduled time
- User account has necessary permissions

**Solution**:

```powershell
# Check task status
Get-ScheduledTask -TaskName "GEMPRA Daily Processing"

# Run task manually
Start-ScheduledTask -TaskName "GEMPRA Daily Processing"
```

### Python Script Errors

**Check**:

- Python is in system PATH
- Required packages are installed
- Working directory is correct

**Solution**:

```powershell
# Verify Python
python --version

# Install dependencies
pip install -r requirements.txt
```

### Git Push Failures

**Check**:

- GitHub credentials are configured
- Network connectivity
- Repository permissions

**Solution**:

```powershell
# Test Git connection
git remote -v
git fetch origin

# Re-configure credentials if needed
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

---

## Security Considerations

### Credentials

- Git credentials stored securely using Windows Credential Manager
- No hardcoded passwords in scripts

### Permissions

- Task runs with user privileges
- Elevated permissions only when necessary

### Network

- HTTPS for Git operations
- Secure API calls to USGS

---

## Performance Metrics

### Typical Execution Time

- Earthquake integration: 2-5 minutes
- Data processing: 3-7 minutes
- Git operations: 1-2 minutes
- **Total**: ~10-15 minutes per run

### Resource Usage

- **CPU**: Moderate during processing
- **Memory**: ~500 MB - 1 GB
- **Network**: ~50-100 MB data transfer
- **Disk**: ~20 MB new data per day
