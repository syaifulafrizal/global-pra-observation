# Automatic Daily Execution Setup

This guide shows how to set up automatic daily execution at 12:00 PM GMT+8.

## Important: Station Processing

**By default, the automation scripts process ALL stations** from `stations.json` automatically. 

- ✅ **All stations**: The daily task will process every station in `stations.json`
- ⚙️ **Specific stations**: If you need to limit to specific stations, you can modify the task action to include `$env:INTERMAGNET_STATIONS="KAK,HER"` before running the script

## Windows Server Setup

### Option 1: Automated Setup (Recommended)

1. **Run the setup script** (as Administrator):
   ```powershell
   # Right-click PowerShell -> Run as Administrator
   cd C:\path\to\pra-observation
   .\setup_windows_scheduler.ps1
   ```

2. **Verify the task was created**:
   ```powershell
   Get-ScheduledTask -TaskName "PRA_Daily_Analysis"
   ```

3. **Test manually** (optional):
   ```powershell
   Start-ScheduledTask -TaskName "PRA_Daily_Analysis"
   ```

### Option 2: Manual Setup via Task Scheduler GUI

1. **Open Task Scheduler**:
   - Press `Win + R`, type `taskschd.msc`, press Enter

2. **Create Basic Task**:
   - Click "Create Basic Task" in right panel
   - Name: `PRA_Daily_Analysis`
   - Description: `Daily PRA Nighttime Analysis at 12:00 PM GMT+8`

3. **Set Trigger**:
   - Trigger: Daily
   - Start: `12:00:00 PM`
   - Recur every: `1 days`

4. **Set Action**:
   - Action: Start a program
   - Program/script: `powershell.exe`
   - Add arguments: `-ExecutionPolicy Bypass -File "C:\path\to\pra-observation\run_daily_analysis.ps1"`
   - Start in: `C:\path\to\pra-observation`

5. **Finish**:
   - Check "Open the Properties dialog" → Finish
   - In Properties:
     - General tab: Check "Run whether user is logged on or not" and "Run with highest privileges"
     - Settings tab: Check "Allow task to be run on demand" and "If the task fails, restart every: 1 minute"

### Keep Flask Server Running

To ensure the web dashboard is always accessible:

**Option A: Run as Windows Service** (Advanced)
- Use NSSM (Non-Sucking Service Manager) to run Flask as a service
- Download: https://nssm.cc/download

**Option B: Monitor Script** (Simple)
```powershell
# Run this in a separate PowerShell window (or as a scheduled task)
.\keep_flask_running.ps1
```

**Option C: Manual Start**
- Just start Flask manually: `python app.py`
- It will run until you close the terminal

---

## Linux Server Setup

### Using Cron

1. **Edit crontab**:
   ```bash
   crontab -e
   ```

2. **Add daily task** (12:00 PM GMT+8 = 04:00 UTC):
   ```cron
   # PRA Daily Analysis - 12:00 PM GMT+8 (04:00 UTC)
   0 4 * * * cd /path/to/pra-observation && /usr/bin/python3 pra_nighttime.py >> logs/daily_analysis.log 2>&1 && /usr/bin/python3 integrate_earthquakes.py >> logs/daily_analysis.log 2>&1 && /usr/bin/python3 upload_results.py >> logs/daily_analysis.log 2>&1
   ```

   Or use the shell script:
   ```bash
   # Create run_daily_analysis.sh
   #!/bin/bash
   cd /path/to/pra-observation
   python3 pra_nighttime.py
   python3 integrate_earthquakes.py
   python3 upload_results.py
   ```

   Then in crontab:
   ```cron
   0 4 * * * /path/to/pra-observation/run_daily_analysis.sh >> /path/to/pra-observation/logs/daily_analysis.log 2>&1
   ```

3. **Keep Flask running** (using systemd):
   ```bash
   # Create /etc/systemd/system/pra-flask.service
   [Unit]
   Description=PRA Flask Web Server
   After=network.target

   [Service]
   Type=simple
   User=your-username
   WorkingDirectory=/path/to/pra-observation
   ExecStart=/usr/bin/python3 app.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

   Enable and start:
   ```bash
   sudo systemctl enable pra-flask.service
   sudo systemctl start pra-flask.service
   ```

---

## Verification

### Check if Task is Running

**Windows**:
```powershell
# View task history
Get-ScheduledTaskInfo -TaskName "PRA_Daily_Analysis"

# View recent logs
Get-Content logs\daily_analysis_*.log -Tail 50
```

**Linux**:
```bash
# Check cron logs
grep CRON /var/log/syslog | tail -20

# Check your logs
tail -f logs/daily_analysis.log
```

### Test the Workflow Manually

```powershell
# Windows
.\run_daily_analysis.ps1

# Linux
./run_daily_analysis.sh
```

---

## Troubleshooting

### Task Not Running

1. **Check Task Scheduler** (Windows):
   - Open Task Scheduler
   - Find "PRA_Daily_Analysis"
   - Check "Last Run Result" (should be 0x0 for success)

2. **Check Logs**:
   - Look in `logs/` directory for error messages

3. **Check Python Path**:
   - Ensure Python is in system PATH
   - Or use full path: `C:\Python\python.exe`

4. **Check Permissions**:
   - Task may need to run as Administrator
   - Or ensure user has write permissions to project directory

### Flask Server Not Accessible

1. **Check if running**:
   ```powershell
   netstat -ano | findstr :5000
   ```

2. **Check firewall**:
   - Windows Firewall may block port 5000
   - Add exception for Python

3. **Check logs**:
   - Flask output shows errors in console

---

## Timezone Notes

- **GMT+8** = Asia/Singapore = Asia/Taipei = Asia/Manila
- Windows Task Scheduler uses **local system time**
- If your server is in GMT+8, set task to 12:00 PM local time
- If server is in different timezone, adjust accordingly:
  - GMT+8 12:00 PM = UTC 04:00 AM
  - GMT+7 12:00 PM = UTC 05:00 AM
  - etc.

---

## Summary

✅ **Windows**: Use `setup_windows_scheduler.ps1` (easiest)
✅ **Linux**: Use cron with `run_daily_analysis.sh`
✅ **Flask**: Run `keep_flask_running.ps1` or use systemd service
✅ **Logs**: Check `logs/` directory for execution history

The system will now run automatically every day at 12:00 PM GMT+8!

