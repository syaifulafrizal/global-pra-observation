# Deployment Workflow Guide

## The Problem

When you ran `deploy_to_github.ps1` directly, it was deploying **old** `web_output/` data that only had 1 station. This happened because:

1. `deploy_to_github.ps1` only deploys what's in `web_output/`
2. It doesn't run `upload_results.py` first to regenerate the files
3. If `upload_results.py` hasn't been run recently, `stations.json` might be outdated

## The Solution

**Always run `upload_results.py` BEFORE deploying!** This script:
- Scans all processed stations
- Regenerates `stations.json` with ALL stations
- Prepares fresh web output files

## Correct Workflow Order

```
1. pra_nighttime.py          → Process all stations
2. integrate_earthquakes.py   → Add earthquake correlations
3. upload_results.py          → Prepare web_output (CRITICAL!)
4. deploy_to_github.ps1      → Deploy to GitHub Pages
```

## Easy Solution: Use the Master Script

### Option 1: Double-Click (Easiest)
Just **double-click `deploy_all.bat`** - it runs everything automatically!

### Option 2: PowerShell
```powershell
.\deploy_all.ps1
```

### Option 3: Manual Steps
If you want to run steps manually:

```powershell
# Step 1: Process all stations
python pra_nighttime.py

# Step 2: Integrate earthquakes
python integrate_earthquakes.py

# Step 3: Prepare web output (CRITICAL!)
python upload_results.py

# Step 4: Deploy to GitHub
$env:GITHUB_REPO = "syaifulafrizal/global-pra-observation"
$env:GITHUB_BRANCH = "gh-pages"
.\deploy_to_github.ps1
```

## What Each Script Does

### `deploy_all.ps1` / `deploy_all.bat`
- **Master script** that runs all steps in order
- Automatically processes all stations
- Regenerates web output with all stations
- Deploys to GitHub Pages
- **Use this for one-click deployment!**

### `deploy_to_github.ps1`
- **Now includes safety checks:**
  - Auto-runs `upload_results.py` if `web_output/` is missing
  - Verifies `stations.json` has multiple stations
  - Regenerates if only 1 station found
- Deploys `web_output/` to GitHub Pages

### `upload_results.py`
- **Critical script** - must run before deployment!
- Scans `web_output/data/*_latest.json` files
- Regenerates `stations.json` with ALL processed stations
- Prepares all web files for deployment

## Verification

After running `upload_results.py`, verify it worked:

```powershell
# Check station count
$json = Get-Content "web_output\data\stations.json" | ConvertFrom-Json
Write-Host "Stations found: $($json.stations.Count)"
```

Should show **51 stations** (or however many you processed), not just 1!

## Troubleshooting

### Problem: Website shows only 1 station after deployment

**Solution:**
1. Run `python upload_results.py` first
2. Verify: `web_output/data/stations.json` has multiple stations
3. Then run `deploy_to_github.ps1`

### Problem: `upload_results.py` only finds 1 station

**Check:**
- Are there multiple `*_latest.json` files in `web_output/data/`?
- Did `pra_nighttime.py` process all stations successfully?
- Check `INTERMAGNET_DOWNLOADS/` for station folders with JSON files

### Problem: Deployment fails

**Check:**
- Is `GITHUB_REPO` environment variable set?
- Do you have push access to the repository?
- Is git configured correctly?

## Quick Reference

| Task | Command |
|------|---------|
| **One-click deploy** | Double-click `deploy_all.bat` |
| **Process stations** | `python pra_nighttime.py` |
| **Add earthquakes** | `python integrate_earthquakes.py` |
| **Prepare web files** | `python upload_results.py` |
| **Deploy to GitHub** | `.\deploy_to_github.ps1` |
| **Test locally** | `python app.py` |

## Summary

✅ **Always use `deploy_all.ps1` or `deploy_all.bat` for deployment**  
✅ **It ensures `upload_results.py` runs first**  
✅ **This prevents the "1 station" problem**  
✅ **One-click solution for complete workflow**

