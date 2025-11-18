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

function Remove-OldDataFiles {
    param([string]$DataDir, [DateTime]$CutoffDate)
    # Remove data files older than cutoff date
    $deletedCount = 0
    
    # Remove old JSON files (format: {station}_{YYYY-MM-DD}.json)
    $jsonFiles = Get-ChildItem -Path $DataDir -Filter "*_*.json" -ErrorAction SilentlyContinue
    foreach ($file in $jsonFiles) {
        if ($file.Name -eq "stations.json") { continue }
        
        # Extract date from filename: {station}_{YYYY-MM-DD}.json
        if ($file.Name -match "_(\d{4}-\d{2}-\d{2})\.json$") {
            $dateStr = $matches[1]
            try {
                $fileDate = [DateTime]::ParseExact($dateStr, "yyyy-MM-dd", $null)
                if ($fileDate -lt $CutoffDate) {
                    Remove-Item -Path $file.FullName -Force -ErrorAction SilentlyContinue
                    $deletedCount++
                }
            } catch {
                # Ignore parse errors
            }
        }
    }
    
    # Remove old figure files
    $figuresDir = Join-Path (Split-Path $DataDir -Parent) "figures"
    if (Test-Path $figuresDir) {
        $stationDirs = Get-ChildItem -Path $figuresDir -Directory -ErrorAction SilentlyContinue
        foreach ($stationDir in $stationDirs) {
            $figFiles = Get-ChildItem -Path $stationDir.FullName -Filter "PRA_*.png" -ErrorAction SilentlyContinue
            foreach ($fig in $figFiles) {
                # Extract date from filename: PRA_{station}_{YYYYMMDD}.png
                if ($fig.Name -match "_(\d{8})\.png$") {
                    $dateStr = $matches[1]
                    try {
                        $fileDate = [DateTime]::ParseExact($dateStr, "yyyyMMdd", $null)
                        if ($fileDate -lt $CutoffDate) {
                            Remove-Item -Path $fig.FullName -Force -ErrorAction SilentlyContinue
                            $deletedCount++
                        }
                    } catch {
                        # Ignore parse errors
                    }
                }
            }
        }
    }
    
    if ($deletedCount -gt 0) {
        Write-Log "Deleted $deletedCount old files (older than $($CutoffDate.ToString('yyyy-MM-dd')))" "Yellow"
    }
    return $deletedCount
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
    Write-Log "  2. Set GITHUB_REPO environment variable" "White"
    Write-Log "  3. Set GITHUB_BRANCH environment variable (gh-pages or main)" "White"
    Write-Log "  4. Optional: Set GITHUB_TOKEN for private repos" "White"
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
            
            # Clean up old files (older than 6 days)
            $cutoffDate = (Get-Date).AddDays(-6).Date
            $dataDir = Join-Path (Get-Location) "data"
            if (Test-Path $dataDir) {
                Write-Log "Cleaning up old data files (keeping last 7 days)..." "Yellow"
                Remove-OldDataFiles -DataDir $dataDir -CutoffDate $cutoffDate
            }
            
            git add -f . 2>&1 | Out-Null
            git commit -m "Initial gh-pages commit" 2>&1 | Out-Null
        } else {
            Write-Log "Switching to gh-pages branch..." "Yellow"
            
            # IMPORTANT: Copy web_output to temp location BEFORE switching branches
            # web_output only exists on main, not on gh-pages
            $tempWebOutput = Join-Path $env:TEMP "web_output_deploy_$(Get-Date -Format 'yyyyMMddHHmmss')"
            if (Test-Path "web_output") {
                Write-Log "Copying web_output to temp location before branch switch..." "Yellow"
                Copy-Item -Path "web_output" -Destination $tempWebOutput -Recurse -Force
            } else {
                Write-Log "web_output not found! Running upload_results.py..." "Yellow"
                python upload_results.py 2>&1 | Out-Null
                if (Test-Path "web_output") {
                    Copy-Item -Path "web_output" -Destination $tempWebOutput -Recurse -Force
                } else {
                    throw "Failed to create web_output. Please run upload_results.py first."
                }
            }
            
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
            
            # Copy from temp location
            if (Test-Path $tempWebOutput) {
                Copy-Item -Path "$tempWebOutput\*" -Destination . -Recurse -Force
                Remove-Item -Path $tempWebOutput -Recurse -Force -ErrorAction SilentlyContinue
            } else {
                throw "Temp web_output not found at $tempWebOutput"
            }
            
            # Clean up old files (older than 6 days)
            $cutoffDate = (Get-Date).AddDays(-6).Date
            $dataDir = Join-Path (Get-Location) "data"
            if (Test-Path $dataDir) {
                Write-Log "Cleaning up old data files (keeping last 7 days)..." "Yellow"
                Remove-OldDataFiles -DataDir $dataDir -CutoffDate $cutoffDate
            }
        }
        
        # Verify we're still on gh-pages before committing
        $verifyBranch = git rev-parse --abbrev-ref HEAD
        if ($verifyBranch -ne "gh-pages") {
            Write-Log "ERROR: Not on gh-pages branch! Current: $verifyBranch" "Red"
            throw "Branch mismatch detected"
        }
        
        # Stage all files at root (but exclude .git and web_output folder)
        Write-Log "Staging files..." "Yellow"
        
        # Add all files except .git and web_output folder
        Get-ChildItem -Path . -Exclude ".git", "web_output" -Recurse -File | ForEach-Object {
            git add -f $_.FullName 2>&1 | Out-Null
        }
        
        # Also add directories (git needs to track empty dirs via .gitkeep or files)
        Get-ChildItem -Path . -Exclude ".git", "web_output" -Directory | ForEach-Object {
            # Add any files in subdirectories
            Get-ChildItem -Path $_.FullName -Recurse -File | ForEach-Object {
                git add -f $_.FullName 2>&1 | Out-Null
            }
        }
        
        # Verify files are staged
        $stagedFiles = git diff --cached --name-only 2>&1
        if ($stagedFiles) {
            $fileList = $stagedFiles -split "`n" | Where-Object { $_ -and $_.Trim() }
            $fileCount = $fileList.Count
            Write-Log "Staged $fileCount files for commit" "Green"
            if ($fileCount -lt 5) {
                Write-Log "Staged files:" "Gray"
                $fileList | ForEach-Object { Write-Log "  - $_" "Gray" }
            }
        } else {
            Write-Log "Warning: No files staged. Checking status..." "Yellow"
            git status 2>&1 | Write-Host
            Write-Log "Attempting to add all files with git add -A..." "Yellow"
            git add -A 2>&1 | Out-Null
            $stagedFiles = git diff --cached --name-only 2>&1
            if ($stagedFiles) {
                $fileCount = ($stagedFiles -split "`n" | Where-Object { $_ }).Count
                Write-Log "Now have $fileCount files staged" "Green"
            }
        }
        
        # Verify we're still on gh-pages before committing
        $verifyBranch = git rev-parse --abbrev-ref HEAD
        if ($verifyBranch -ne "gh-pages") {
            Write-Log "ERROR: Not on gh-pages branch! Current: $verifyBranch" "Red"
            throw "Branch mismatch detected"
        }
        
        
    } else {
        git checkout $GITHUB_BRANCH 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to checkout $GITHUB_BRANCH branch"
        }
        # For non-gh-pages branches, just add web_output as-is
        git add -f web_output/ 2>&1 | Out-Null
    }
    
    # Ensure git user is configured
    $gitUser = git config user.name 2>&1
    $gitEmail = git config user.email 2>&1
    if (-not $gitUser -or $gitUser -match "error") {
        Write-Log "Configuring git user..." "Yellow"
        git config user.name "PRA Automation" 2>&1 | Out-Null
        git config user.email "pra@localhost" 2>&1 | Out-Null
    }
    if (-not $gitEmail -or $gitEmail -match "error") {
        git config user.email "pra@localhost" 2>&1 | Out-Null
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
        $commitOutput = git commit -m $commitMessage 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Commit output: $commitOutput" "Red"
            Write-Log "Checking git status..." "Yellow"
            git status 2>&1 | Write-Host
            throw "Failed to commit changes. Exit code: $LASTEXITCODE"
        }
        Write-Log "Commit successful" "Green"
    } else {
        Write-Log "No file changes detected, creating empty commit to update timestamp..." "Yellow"
        $commitOutput = git commit --allow-empty -m $commitMessage 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Commit output: $commitOutput" "Red"
            throw "Failed to create empty commit. Exit code: $LASTEXITCODE"
        }
        Write-Log "Empty commit created successfully" "Green"
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
