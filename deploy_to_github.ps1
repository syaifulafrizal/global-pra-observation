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
    Write-Log "Running upload_results.py to prepare files..." "Yellow"
    python upload_results.py
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ERROR: Failed to prepare web output!" "Red"
        exit 1
    }
    Write-Log "Web output prepared successfully" "Green"
}

# Verify stations.json exists and has multiple stations
$stationsJson = "web_output\data\stations.json"
if (Test-Path $stationsJson) {
    try {
        $jsonContent = Get-Content $stationsJson | ConvertFrom-Json
        $stationCount = if ($jsonContent.stations) { $jsonContent.stations.Count } else { 0 }
        if ($stationCount -le 1) {
            Write-Log "WARNING: Only $stationCount station(s) in stations.json!" "Yellow"
            Write-Log "Regenerating web output to ensure all stations are included..." "Yellow"
            python upload_results.py
            if ($LASTEXITCODE -eq 0) {
                $jsonContent = Get-Content $stationsJson | ConvertFrom-Json
                $stationCount = if ($jsonContent.stations) { $jsonContent.stations.Count } else { 0 }
                Write-Log "After regeneration: $stationCount stations found" "Green"
            }
        } else {
            Write-Log "Verified: $stationCount stations ready for deployment" "Green"
        }
    } catch {
        Write-Log "WARNING: Could not verify stations.json, but continuing..." "Yellow"
    }
} else {
    Write-Log "WARNING: stations.json not found, regenerating web output..." "Yellow"
    python upload_results.py
    if ($LASTEXITCODE -ne 0) {
        Write-Log "ERROR: Failed to prepare web output!" "Red"
        exit 1
    }
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

# Save current branch
$currentBranch = git rev-parse --abbrev-ref HEAD

# Step 1: Commit and push main branch changes first (if on main)
if ($currentBranch -eq "main" -or $currentBranch -eq "master") {
    Write-Log "Checking for uncommitted changes on $currentBranch branch..." "Yellow"
    $status = git status --porcelain
    if ($status) {
        Write-Log "Found uncommitted changes on $currentBranch, committing..." "Yellow"
        
        # Stage all changes (except web_output which is in .gitignore)
        git add -A 2>&1 | Out-Null
        git reset HEAD web_output/ 2>&1 | Out-Null  # Don't commit web_output to main
        
        $mainCommitMsg = "Update source files - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        git commit -m $mainCommitMsg 2>&1 | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Pushing $currentBranch branch to origin..." "Yellow"
            git push origin $currentBranch 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Log "Successfully pushed $currentBranch branch" "Green"
            } else {
                Write-Log "Warning: Failed to push $currentBranch (continuing with deployment)" "Yellow"
            }
        }
    } else {
        Write-Log "No uncommitted changes on $currentBranch branch" "Green"
    }
}

# Fetch latest from remote
Write-Log "Fetching latest from remote..." "Yellow"
git fetch origin 2>&1 | Out-Null

# Push to GitHub
Write-Log "Deploying to GitHub Pages..." "Yellow"
try {
    if ($GITHUB_BRANCH -eq "gh-pages") {
        # Check if remote branch exists
        $remoteBranchExists = git branch -r | Select-String -Pattern "origin/gh-pages"
        $localBranchExists = git branch | Select-String -Pattern "^\s*gh-pages$"
        
        if (-not $remoteBranchExists) {
            # Create orphan branch for gh-pages (first time only)
            Write-Log "Creating gh-pages branch..." "Yellow"
            
            # Stash any uncommitted changes
            $hasChanges = git status --porcelain
            if ($hasChanges) {
                Write-Log "Stashing uncommitted changes..." "Yellow"
                git stash push -m "Auto-stash before gh-pages deployment" 2>&1 | Out-Null
            }
            
            git checkout --orphan gh-pages 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to create gh-pages branch"
            }
            git rm -rf --cached . 2>&1 | Out-Null
            
            # Copy web_output contents to root (GitHub Pages needs files at root)
            Write-Log "Copying web_output files to root..." "Yellow"
            if (Test-Path "web_output") {
                Copy-Item -Path "web_output\*" -Destination . -Recurse -Force
            }
            
            git add -f . 2>&1 | Out-Null
            git commit -m "Initial gh-pages commit" 2>&1 | Out-Null
        } else {
            Write-Log "Switching to gh-pages branch..." "Yellow"
            
            # Stash any uncommitted changes before switching
            $hasChanges = git status --porcelain
            if ($hasChanges) {
                Write-Log "Stashing uncommitted changes..." "Yellow"
                git stash push -m "Auto-stash before gh-pages deployment" 2>&1 | Out-Null
            }
            
            # Try to checkout existing local branch
            if ($localBranchExists) {
                git checkout gh-pages 2>&1 | Out-Null
            } else {
                # Create local branch tracking remote
                git checkout -b gh-pages origin/gh-pages 2>&1 | Out-Null
            }
            
            if ($LASTEXITCODE -ne 0) {
                # Force checkout by resetting the branch
                Write-Log "Force resetting gh-pages branch..." "Yellow"
                if ($localBranchExists) {
                    git branch -D gh-pages 2>&1 | Out-Null
                }
                git checkout -b gh-pages origin/gh-pages 2>&1 | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    throw "Failed to checkout gh-pages branch"
                }
            }
            
            # Verify we're on gh-pages
            $checkBranch = git rev-parse --abbrev-ref HEAD
            if ($checkBranch -ne "gh-pages") {
                throw "Not on gh-pages branch! Current: $checkBranch"
            }
            
            # Copy web_output contents to root
            Write-Log "Copying web_output files to root..." "Yellow"
            # Remove existing files (except .git and web_output)
            Get-ChildItem -Path . -Exclude ".git", "web_output" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
            if (Test-Path "web_output") {
                Copy-Item -Path "web_output\*" -Destination . -Recurse -Force
            }
        }
        
        # Verify we're still on gh-pages before committing
        $verifyBranch = git rev-parse --abbrev-ref HEAD
        if ($verifyBranch -ne "gh-pages") {
            Write-Log "ERROR: Not on gh-pages branch! Current: $verifyBranch" "Red"
            throw "Branch mismatch detected"
        }
        
        # Stage all files at root
        Write-Log "Staging files..." "Yellow"
        git add -f . 2>&1 | Out-Null
        # Remove web_output from staging (we don't want the folder, just its contents at root)
        git reset HEAD web_output/ 2>&1 | Out-Null
        
    } else {
        git checkout $GITHUB_BRANCH 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to checkout $GITHUB_BRANCH branch"
        }
        # For non-gh-pages branches, just add web_output as-is
        git add -f web_output/ 2>&1 | Out-Null
    }
    
    # Check if there are changes
    $status = git status --porcelain
    $hasChanges = $status -and ($status.Trim().Length -gt 0)
    
    # Commit changes (or create empty commit if no changes)
    $commitMessage = "Update web output - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    
    # Final verification of branch before commit
    $finalBranch = git rev-parse --abbrev-ref HEAD
    Write-Log "Committing on branch: $finalBranch" "Cyan"
    
    if ($hasChanges) {
        Write-Log "Committing changes..." "Yellow"
        git commit -m $commitMessage 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to commit changes"
        }
    } else {
        Write-Log "No file changes detected, creating empty commit to update timestamp..." "Yellow"
        git commit --allow-empty -m $commitMessage 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create empty commit"
        }
    }
    
    Write-Log "Pushing to origin/$GITHUB_BRANCH..." "Yellow"
    $pushOutput = git push -u origin $GITHUB_BRANCH --force 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Push output: $pushOutput" "Red"
        throw "Failed to push to GitHub"
    }
    
    Write-Log "SUCCESS: Deployed to GitHub!" "Green"
    Write-Log "" "White"
    Write-Log "Your site will be available at:" "Cyan"
    if ($GITHUB_REPO -match "github.com/(.+)") {
        $repoPath = $matches[1] -replace "\.git$", ""
    } else {
        $repoPath = $GITHUB_REPO -replace "\.git$", "" -replace "https://github.com/", ""
    }
    # Format: username/repo -> https://username.github.io/repo
    $parts = $repoPath -split "/"
    if ($parts.Length -eq 2) {
        $username = $parts[0]
        $repoName = $parts[1]
        Write-Log "  https://$username.github.io/$repoName" "Green"
    } else {
        Write-Log "  https://$repoPath.github.io" "Green"
    }
    Write-Log "" "White"
    Write-Log "Note: It may take 1-2 minutes for GitHub Pages to update" "Yellow"
    
    # Switch back to original branch
    if ($currentBranch -and $currentBranch -ne $GITHUB_BRANCH) {
        Write-Log "Switching back to $currentBranch branch..." "Yellow"
        git checkout $currentBranch 2>&1 | Out-Null
        
        # Restore stashed changes if any
        $stashList = git stash list 2>&1
        if ($stashList -match "Auto-stash before gh-pages deployment") {
            Write-Log "Restoring stashed changes..." "Yellow"
            git stash pop 2>&1 | Out-Null
        }
    }
    
} catch {
    Write-Log "ERROR: Failed to deploy" "Red"
    Write-Log $_.Exception.Message "Red"
    Write-Log "" "White"
    Write-Log "Troubleshooting:" "Yellow"
    Write-Log "  1. Check GITHUB_REPO is correct" "White"
    Write-Log "  2. Ensure you have push access" "White"
    Write-Log "  3. For private repos, set GITHUB_TOKEN" "White"
    Write-Log "  4. Check git status: git status" "White"
    Write-Log "  5. Check current branch: git branch" "White"
    
    # Try to switch back to original branch
    if ($currentBranch) {
        Write-Log "Switching back to $currentBranch branch..." "Yellow"
        git checkout $currentBranch 2>&1 | Out-Null
        
        # Restore stashed changes if any
        $stashList = git stash list 2>&1
        if ($stashList -match "Auto-stash before gh-pages deployment") {
            Write-Log "Restoring stashed changes..." "Yellow"
            git stash pop 2>&1 | Out-Null
        }
    }
    exit 1
}

