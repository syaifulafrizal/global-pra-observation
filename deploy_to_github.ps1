# Deploy Web Output to GitHub Pages
# This script pushes the web_output/ directory to GitHub for public hosting
# Designed to run after processing completes

$ErrorActionPreference = "Continue"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Configuration
$GITHUB_REPO = $env:GITHUB_REPO  # e.g., "username/pra-observation" or full URL
$GITHUB_BRANCH = $env:GITHUB_BRANCH  # e.g., "gh-pages" or "main"
$GITHUB_TOKEN = $env:GITHUB_TOKEN  # Personal access token (optional, for private repos)

function Write-Log {
    param([string]$Message, [string]$Color = "White")
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$Timestamp] $Message" -ForegroundColor $Color
}

Write-Log "==========================================" "Cyan"
Write-Log "GitHub Pages Deployment" "Cyan"
Write-Log "==========================================" "Cyan"

# Check if web_output exists
if (-not (Test-Path "web_output")) {
    Write-Log "ERROR: web_output/ directory not found!" "Red"
    Write-Log "Run 'python upload_results.py' first to prepare files" "Yellow"
    exit 1
}

# Check if git is initialized
if (-not (Test-Path ".git")) {
    Write-Log "Initializing git repository..." "Yellow"
    git init
    git config user.name "PRA Automation" 2>$null
    git config user.email "pra@localhost" 2>$null
}

# Check if GitHub repo is configured
if (-not $GITHUB_REPO) {
    Write-Log "WARNING: GITHUB_REPO environment variable not set" "Yellow"
    Write-Log "Skipping GitHub deployment" "Yellow"
    Write-Log "" "White"
    Write-Log "To enable GitHub Pages deployment:" "Cyan"
    Write-Log "  1. Create a GitHub repository" "White"
    Write-Log "  2. Set: `$env:GITHUB_REPO='username/repo-name'" "White"
    Write-Log "  3. Set: `$env:GITHUB_BRANCH='gh-pages' (or 'main')" "White"
    Write-Log "  4. Optional: `$env:GITHUB_TOKEN='your-token' (for private repos)" "White"
    exit 0
}

# Determine branch (default: gh-pages for GitHub Pages)
if (-not $GITHUB_BRANCH) {
    $GITHUB_BRANCH = "gh-pages"
}

Write-Log "Repository: $GITHUB_REPO" "Green"
Write-Log "Branch: $GITHUB_BRANCH" "Green"

# Check if remote exists
$remoteExists = git remote | Select-String -Pattern "origin"
if (-not $remoteExists) {
    Write-Log "Adding GitHub remote..." "Yellow"
    if ($GITHUB_REPO -notmatch "^https://") {
        $GITHUB_REPO = "https://github.com/$GITHUB_REPO.git"
    }
    git remote add origin $GITHUB_REPO
}

# Update remote URL if token provided
if ($GITHUB_TOKEN) {
    Write-Log "Using GitHub token for authentication..." "Yellow"
    $repoUrl = git remote get-url origin
    if ($repoUrl -match "https://github.com/(.+)") {
        $repoPath = $matches[1]
        git remote set-url origin "https://$GITHUB_TOKEN@github.com/$repoPath"
    }
}

# Stage web_output files
Write-Log "Staging web_output files..." "Yellow"
git add web_output/
git add web_output/**/*

# Check if there are changes
$status = git status --porcelain
if (-not $status) {
    Write-Log "No changes to deploy" "Yellow"
    exit 0
}

# Commit changes
$commitMessage = "Update web output - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Log "Committing changes..." "Yellow"
git commit -m $commitMessage 2>&1 | Out-Null

# Push to GitHub
Write-Log "Pushing to GitHub..." "Yellow"
try {
    if ($GITHUB_BRANCH -eq "gh-pages") {
        # Create orphan branch for gh-pages (first time only)
        $branchExists = git branch -r | Select-String -Pattern "origin/gh-pages"
        if (-not $branchExists) {
            Write-Log "Creating gh-pages branch..." "Yellow"
            git checkout --orphan gh-pages 2>&1 | Out-Null
            git rm -rf --cached . 2>&1 | Out-Null
            git add web_output/ 2>&1 | Out-Null
            git commit -m "Initial gh-pages commit" 2>&1 | Out-Null
        } else {
            git checkout gh-pages 2>&1 | Out-Null
        }
    } else {
        git checkout $GITHUB_BRANCH 2>&1 | Out-Null
    }
    
    git push -u origin $GITHUB_BRANCH --force 2>&1 | Out-Null
    
    Write-Log "SUCCESS: Deployed to GitHub!" "Green"
    Write-Log "" "White"
    Write-Log "Your site will be available at:" "Cyan"
    if ($GITHUB_REPO -match "github.com/(.+)") {
        $repoPath = $matches[1] -replace "\.git$", ""
        Write-Log "  https://$repoPath.github.io" "Green"
    } else {
        $repoPath = $GITHUB_REPO -replace "\.git$", "" -replace "https://github.com/", ""
        Write-Log "  https://$repoPath.github.io" "Green"
    }
    Write-Log "" "White"
    Write-Log "Note: It may take 1-2 minutes for GitHub Pages to update" "Yellow"
    
} catch {
    Write-Log "ERROR: Failed to push to GitHub" "Red"
    Write-Log $_.Exception.Message "Red"
    Write-Log "" "White"
    Write-Log "Troubleshooting:" "Yellow"
    Write-Log "  1. Check GITHUB_REPO is correct" "White"
    Write-Log "  2. Ensure you have push access" "White"
    Write-Log "  3. For private repos, set GITHUB_TOKEN" "White"
    exit 1
}

