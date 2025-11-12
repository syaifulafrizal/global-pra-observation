# GitHub Pages Deployment Guide

## Overview

This guide shows how to deploy your PRA frontend to **GitHub Pages** for free public hosting, while keeping processing on your local server PC.

## Architecture

```
┌─────────────────┐         ┌──────────────┐
│  Your Server PC │         │  GitHub      │
│                 │         │              │
│  1. Processing  │────────▶│  GitHub Pages │
│  2. Upload      │  Git    │  (Frontend)  │
│                 │  Push   │              │
└─────────────────┘         └──────────────┘
                                      │
                                      ▼
                              Public Website
                         (https://username.github.io/repo)
```

**Benefits**:
- ✅ **Free** static hosting
- ✅ **Automatic updates** after processing
- ✅ **Public access** via GitHub Pages URL
- ✅ **Processing stays local** (your server PC)
- ✅ **No cloud costs**

---

## Setup Instructions

### Step 1: Create GitHub Repository

1. Go to [GitHub](https://github.com) and create a new repository
   - Name: `pra-observation` (or any name)
   - Visibility: **Public** (required for free GitHub Pages)
   - **Do NOT** initialize with README (we'll push existing code)

2. Note your repository path: `username/repo-name`

---

### Step 2: Initialize Git (if not already done)

```powershell
# Windows
cd C:\Users\SYAIFUL\Downloads\pra-observation
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/username/repo-name.git
git push -u origin main
```

```bash
# Linux
cd /path/to/pra-observation
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/username/repo-name.git
git push -u origin main
```

---

### Step 3: Configure GitHub Deployment

Set environment variables for automatic deployment:

**Windows (PowerShell)**:
```powershell
# Set permanently (for current user)
[System.Environment]::SetEnvironmentVariable('GITHUB_REPO', 'username/repo-name', 'User')
[System.Environment]::SetEnvironmentVariable('GITHUB_BRANCH', 'gh-pages', 'User')

# Or set temporarily (current session only)
$env:GITHUB_REPO = "username/repo-name"
$env:GITHUB_BRANCH = "gh-pages"
```

**Linux/Mac**:
```bash
# Add to ~/.bashrc or ~/.zshrc
export GITHUB_REPO="username/repo-name"
export GITHUB_BRANCH="gh-pages"
```

**Optional: For Private Repositories**

If your repo is private, you'll need a GitHub Personal Access Token:

1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token with `repo` scope
3. Set environment variable:

```powershell
# Windows
[System.Environment]::SetEnvironmentVariable('GITHUB_TOKEN', 'your-token-here', 'User')
```

```bash
# Linux
export GITHUB_TOKEN="your-token-here"
```

---

### Step 4: Enable GitHub Pages

1. Go to your repository on GitHub
2. Settings → Pages
3. Source: Select **`gh-pages`** branch
4. Folder: `/ (root)`
5. Click **Save**

Your site will be available at:
```
https://username.github.io/repo-name
```

---

### Step 5: Test Deployment

**Manual Test**:
```powershell
# Windows
python upload_results.py
.\deploy_to_github.ps1
```

```bash
# Linux
python3 upload_results.py
bash deploy_to_github.sh
```

**Check**:
- Visit your GitHub Pages URL (may take 1-2 minutes to update)
- Verify files are in `web_output/` directory on `gh-pages` branch

---

### Step 6: Automatic Daily Deployment

The daily workflow (`run_daily_analysis.ps1`) will automatically deploy to GitHub after processing completes, **if** `GITHUB_REPO` is set.

**Workflow**:
1. Process stations (12:00 PM GMT+8)
2. Integrate earthquakes
3. Prepare web files
4. **Deploy to GitHub Pages** ← Automatic!

---

## Alternative: Netlify Drop

If you prefer not to use GitHub:

### Netlify Drop (No Git Required)

1. Go to [Netlify Drop](https://app.netlify.com/drop)
2. Drag and drop your `web_output/` folder
3. Get instant public URL
4. **Manual updates**: Drag and drop again after each processing run

**Pros**: Super simple, no Git needed
**Cons**: Manual updates only

---

## Alternative: Cloudflare Pages

Similar to GitHub Pages:

1. Create Cloudflare account
2. Connect GitHub repository
3. Build command: `python upload_results.py`
4. Output directory: `web_output`
5. Automatic deployments on push

---

## Troubleshooting

### "GITHUB_REPO not set"

**Solution**: Set the environment variable (see Step 3)

### "Permission denied" or "Authentication failed"

**Solutions**:
- For public repos: Ensure you have push access
- For private repos: Set `GITHUB_TOKEN` with `repo` scope
- Check: `git remote -v` shows correct URL

### "gh-pages branch not found"

**Solution**: The script will create it automatically on first run. If it fails:
```bash
git checkout --orphan gh-pages
git rm -rf --cached .
git add web_output/
git commit -m "Initial gh-pages"
git push -u origin gh-pages
```

### GitHub Pages shows 404

**Solutions**:
1. Wait 1-2 minutes (GitHub needs time to build)
2. Check Settings → Pages → Source is set to `gh-pages`
3. Verify `web_output/index.html` exists in `gh-pages` branch
4. Check Actions tab for build errors

### Files not updating

**Solutions**:
1. Check if `web_output/` has new files after `upload_results.py`
2. Verify git commit was created (check `git log`)
3. Check if push succeeded (no errors in script output)
4. Clear browser cache

---

## Manual Deployment (Without Automation)

If you want to deploy manually after processing:

```powershell
# 1. Process data
python pra_nighttime.py
python integrate_earthquakes.py

# 2. Prepare web files
python upload_results.py

# 3. Deploy to GitHub
.\deploy_to_github.ps1
```

---

## File Structure on GitHub

After deployment, your `gh-pages` branch will contain:

```
gh-pages/
├── index.html          (Main dashboard)
├── static/
│   ├── app.js          (Frontend JavaScript)
│   └── style.css       (Styles)
├── data/
│   ├── stations.json   (Station metadata)
│   ├── _latest.json    (Latest results)
│   ├── _anomalies.csv  (Anomaly data)
│   └── _earthquake_correlations.csv
└── figures/
    └── [station]/
        └── PRA_*.png   (Generated plots)
```

---

## Summary

✅ **Processing**: Runs locally on your server PC  
✅ **Frontend**: Hosted on GitHub Pages (free)  
✅ **Updates**: Automatic after daily processing  
✅ **Access**: Public URL via GitHub Pages  
✅ **Cost**: $0 (completely free)

Your workflow:
1. Daily processing runs at 12:00 PM GMT+8
2. Results prepared in `web_output/`
3. Automatically pushed to GitHub
4. Website updates within 1-2 minutes

---

## Next Steps

1. ✅ Set up GitHub repository
2. ✅ Configure `GITHUB_REPO` environment variable
3. ✅ Enable GitHub Pages in repository settings
4. ✅ Test deployment manually
5. ✅ Let daily automation handle updates!

Your site will be live at: `https://username.github.io/repo-name`

