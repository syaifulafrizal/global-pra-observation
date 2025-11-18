# Deploy Web Output to GitHub Pages
# This script pushes the web_output/ directory to GitHub for public hosting
# Designed to run after processing completes

$ErrorActionPreference = "Continue"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Configuration
$GITHUB_REPO = if ($env:GITHUB_REPO) { $env:GITHUB_REPO } else { "https://github.com/syaifulafrizal/global-pra-observation.git" }
$GITHUB_BRANCH = if ($env:GITHUB_BRANCH) { $env:GITHUB_BRANCH } else { "gh-pages" }
$GITHUB_TOKEN = $env:GITHUB_TOKEN

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

# Function to remove old data files
function Remove-OldDataFiles {
    param(
        [string]$DataDir,
        [datetime]$CutoffDate
    )
    
    $deletedCount = 0
    if (Test-Path $DataDir) {
        Get-ChildItem -Path $DataDir -Filter "*.json" | Where-Object {
            $_.LastWriteTime -lt $CutoffDate
        } | ForEach-Object {
            Write-Log "  Deleting old file: $($_.Name)" "Gray"
            Remove-Item $_.FullName -Force
            $deletedCount++
        }
        
        Get-ChildItem -Path $DataDir -Filter "*.png" | Where-Object {
            $_.LastWriteTime -lt $CutoffDate
        } | ForEach-Object {
            Write-Log "  Deleting old file: $($_.Name)" "Gray"
            Remove-Item $_.FullName -Force
            $deletedCount++
        }
    }
    return $deletedCount
}

# Configure remote - always ensure it's set correctly with full URL
$remotes = git remote 2>&1

# Normalize GITHUB_REPO to full URL format
$normalizedRepo = if ($GITHUB_REPO -match "^https://github\.com/") {
    # Already a full URL, ensure it ends with .git
    if ($GITHUB_REPO -notmatch "\.git$") {
        "$GITHUB_REPO.git"
    } else {
        $GITHUB_REPO
    }
} elseif ($GITHUB_REPO -match "^github\.com/") {
    # Missing https:// prefix
    "https://$GITHUB_REPO"
} elseif ($GITHUB_REPO -match "^[^/]+/[^/]+$") {
    # Just username/repo format
    "https://github.com/$GITHUB_REPO.git"
} else {
    # Assume it's already correct or use default
    $GITHUB_REPO
}

# Build expected URL (with token if provided)
$expectedUrl = if ($GITHUB_TOKEN) {
    if ($normalizedRepo -match "https://github\.com/(.+)") {
        $repoPath = $matches[1] -replace "\.git$", ""
        "https://$GITHUB_TOKEN@github.com/$repoPath.git"
    } else {
        $normalizedRepo
    }
} else {
    $normalizedRepo
}

Write-Log "Repository: $normalizedRepo" "White"
Write-Log "Branch: $GITHUB_BRANCH" "White"
Write-Log "" "White"

if ($remotes -notmatch "origin") {
    Write-Log "Adding remote origin..." "Yellow"
    git remote add origin $expectedUrl
} else {
    Write-Log "Updating remote origin URL..." "Yellow"
    git remote set-url origin $expectedUrl
    # Verify it was set correctly
    $verifyUrl = git remote get-url origin 2>&1
    if ($verifyUrl -ne $expectedUrl -and -not ($verifyUrl -match "error")) {
        Write-Log "Warning: Remote URL mismatch. Setting again..." "Yellow"
        git remote set-url origin $expectedUrl --push
        git remote set-url origin $expectedUrl
    }
    Write-Log "Remote URL verified: $expectedUrl" "Gray"
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

# Save current branch
$currentBranch = git rev-parse --abbrev-ref HEAD

# Fetch latest from remote
Write-Log "Fetching latest from remote..." "Yellow"
git fetch origin 2>&1 | Out-Null

# IMPORTANT: Copy web_output to temp location BEFORE switching branches
# web_output is in .gitignore, so it won't exist on gh-pages branch
Write-Log "Preparing web_output for deployment..." "Yellow"
if (-not (Test-Path "web_output")) {
    Write-Log "ERROR: web_output/ directory not found on current branch!" "Red"
    Write-Log "Please run 'python upload_results.py' first to prepare files" "Red"
    exit 1
}

# Verify web_output/data/stations.json has correct format
if (Test-Path "web_output/data/stations.json") {
    try {
        $webOutputJson = Get-Content "web_output/data/stations.json" | ConvertFrom-Json
        $webOutputCount = if ($webOutputJson.stations) { $webOutputJson.stations.Count } else { 0 }
        $webOutputHasDates = $webOutputJson.available_dates -ne $null
        
        Write-Log "web_output verification:" "Yellow"
        Write-Log "  Stations: $webOutputCount" "Gray"
        Write-Log "  Has available_dates: $webOutputHasDates" "Gray"
        
        if ($webOutputCount -le 1 -or -not $webOutputHasDates) {
            Write-Log "ERROR: web_output/data/stations.json has wrong format!" "Red"
            Write-Log "Please run 'python upload_results.py' again to regenerate it" "Red"
            exit 1
        } else {
            Write-Log "Verified: web_output is correct ($webOutputCount stations)" "Green"
        }
    } catch {
        Write-Log "ERROR: Could not verify web_output/data/stations.json: $_" "Red"
        exit 1
    }
} else {
    Write-Log "ERROR: web_output/data/stations.json not found!" "Red"
    Write-Log "Please run 'python upload_results.py' first" "Red"
    exit 1
}

# Copy web_output to temp location (outside .gitignore) so it persists across branch switches
# Use absolute path in parent directory to ensure it persists across branch switches
$repoRoot = (Get-Location).Path
$parentDir = Split-Path -Parent $repoRoot
$tempWebOutput = Join-Path $parentDir "web_output_temp_deploy_$(Split-Path -Leaf $repoRoot)"
$tempStationsJson = Join-Path $parentDir "stations_json_temp_$(Split-Path -Leaf $repoRoot).json"

Write-Log "Copying web_output to temp location for branch switching..." "Yellow"
Write-Log "  Temp location: $tempWebOutput" "Gray"
Write-Log "  Temp stations.json: $tempStationsJson" "Gray"

if (Test-Path $tempWebOutput) {
    Remove-Item $tempWebOutput -Recurse -Force
}
Copy-Item -Path "web_output" -Destination $tempWebOutput -Recurse -Force

# Also copy stations.json to a single file that will persist (not in a directory)
if (Test-Path "web_output/data/stations.json") {
    Copy-Item -Path "web_output/data/stations.json" -Destination $tempStationsJson -Force
    Write-Log "Copied stations.json to temp file (will persist across branch switch)" "Green"
}

Write-Log "web_output copied to temp location (will be used after branch switch)" "Green"

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
            
            # Pull latest from remote to ensure we're up to date
            Write-Log "Pulling latest from origin/gh-pages..." "Yellow"
            git pull origin gh-pages 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Log "Warning: Failed to pull from remote (continuing anyway)" "Yellow"
            }
            
            # Copy web_output contents to root
            Write-Log "Copying web_output files to root..." "Yellow"
            # Remove existing files (except .git and web_output) - be more aggressive
            Write-Log "Removing old files from root..." "Yellow"
            Get-ChildItem -Path . -Exclude ".git", "web_output" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
            
            # Also remove any old index.html or static/ directory that might exist
            if (Test-Path "index.html") {
                Remove-Item "index.html" -Force -ErrorAction SilentlyContinue
            }
            if (Test-Path "static") {
                Remove-Item "static" -Recurse -Force -ErrorAction SilentlyContinue
            }
            if (Test-Path "data") {
                Remove-Item "data" -Recurse -Force -ErrorAction SilentlyContinue
            }
            if (Test-Path "figures") {
                Remove-Item "figures" -Recurse -Force -ErrorAction SilentlyContinue
            }
            
            # Copy from temp web_output location (web_output doesn't exist on gh-pages branch)
            # Use absolute path in parent directory (persists across branch switches)
            $repoRoot = (Get-Location).Path
            $parentDir = Split-Path -Parent $repoRoot
            $tempWebOutput = Join-Path $parentDir "web_output_temp_deploy_$(Split-Path -Leaf $repoRoot)"
            $tempStationsJson = Join-Path $parentDir "stations_json_temp_$(Split-Path -Leaf $repoRoot).json"
            
            Write-Log "Looking for temp files..." "Yellow"
            Write-Log "  Temp location: $tempWebOutput" "Gray"
            Write-Log "  Temp stations.json: $tempStationsJson" "Gray"
            
            # First, try to restore stations.json from the temp file (most reliable)
            if (Test-Path $tempStationsJson) {
                Write-Log "Found temp stations.json file, will use it after copying..." "Green"
            } else {
                Write-Log "Temp stations.json not found at: $tempStationsJson" "Yellow"
            }
            
            if (Test-Path $tempWebOutput) {
                Write-Log "Copying files from temp web_output to root..." "Yellow"
                # Copy all contents of temp web_output to current directory
                $webOutputPath = Resolve-Path $tempWebOutput
                Get-ChildItem -Path $webOutputPath -Force | ForEach-Object {
                    $destPath = Join-Path (Get-Location) $_.Name
                    if ($_.PSIsContainer) {
                        Copy-Item -Path $_.FullName -Destination $destPath -Recurse -Force
                    } else {
                        Copy-Item -Path $_.FullName -Destination $destPath -Force
                    }
                }
                Write-Log "Files copied successfully from temp location" "Green"
                
                # Overwrite stations.json with the temp file if it exists (ensures correct format)
                if (Test-Path $tempStationsJson) {
                    if (Test-Path "data/stations.json") {
                        Copy-Item -Path $tempStationsJson -Destination "data/stations.json" -Force
                        Write-Log "Overwrote stations.json with temp file (ensuring correct format)" "Green"
                    } else {
                        # Create data directory if it doesn't exist
                        if (-not (Test-Path "data")) {
                            New-Item -Path "data" -ItemType Directory -Force | Out-Null
                        }
                        Copy-Item -Path $tempStationsJson -Destination "data/stations.json" -Force
                        Write-Log "Created data/stations.json from temp file" "Green"
                    }
                }
            } elseif (Test-Path "web_output") {
                # Fallback: try web_output if temp doesn't exist
                Write-Log "Temp web_output not found, trying web_output directory..." "Yellow"
                $webOutputPath = Resolve-Path "web_output"
                Get-ChildItem -Path $webOutputPath -Force | ForEach-Object {
                    $destPath = Join-Path (Get-Location) $_.Name
                    if ($_.PSIsContainer) {
                        Copy-Item -Path $_.FullName -Destination $destPath -Recurse -Force
                    } else {
                        Copy-Item -Path $_.FullName -Destination $destPath -Force
                    }
                }
                Write-Log "Files copied successfully" "Green"
                
                # Also try to use temp stations.json if available
                if (Test-Path $tempStationsJson) {
                    if (Test-Path "data/stations.json") {
                        Copy-Item -Path $tempStationsJson -Destination "data/stations.json" -Force
                        Write-Log "Overwrote stations.json with temp file" "Green"
                    }
                }
            } else {
                throw "Neither temp web_output nor web_output directory found"
            }
            
            # Verify critical files exist and have correct content
            $criticalFiles = @('index.html', 'static/app.js', 'static/style.css', 'data/stations.json')
            $missingFiles = @()
            foreach ($file in $criticalFiles) {
                if (-not (Test-Path $file)) {
                    $missingFiles += $file
                }
            }
            if ($missingFiles.Count -gt 0) {
                Write-Log "ERROR: Missing critical files after copy: $($missingFiles -join ', ')" "Red"
                throw "Critical files missing after copy"
            } else {
                Write-Log "Verified: All critical files are present" "Green"
            }
            
            # Verify stations.json has correct format (not old format)
            try {
                $stationsJson = Get-Content "data/stations.json" | ConvertFrom-Json
                $stationCount = if ($stationsJson.stations) { $stationsJson.stations.Count } else { 0 }
                $hasAvailableDates = $stationsJson.available_dates -ne $null
                $hasMetadata = $stationsJson.metadata -ne $null
                
                Write-Log "Verifying stations.json content..." "Yellow"
                Write-Log "  Stations: $stationCount" "Gray"
                Write-Log "  Has available_dates: $hasAvailableDates" "Gray"
                Write-Log "  Has metadata: $hasMetadata" "Gray"
                
                if ($stationCount -le 1 -or -not $hasAvailableDates) {
                    Write-Log "ERROR: stations.json has old format! (Stations: $stationCount, Has dates: $hasAvailableDates)" "Red"
                    Write-Log "This suggests web_output/data/stations.json wasn't copied correctly" "Red"
                    Write-Log "Note: web_output may not exist on gh-pages branch (it's in .gitignore)" "Yellow"
                    Write-Log "Re-copying from temp stations.json file..." "Yellow"
                    
                    # Try temp stations.json file first (most reliable)
                    # Use absolute path in parent directory
                    $repoRoot = (Get-Location).Path
                    $parentDir = Split-Path -Parent $repoRoot
                    $tempStationsJson = Join-Path $parentDir "stations_json_temp_$(Split-Path -Leaf $repoRoot).json"
                    if (Test-Path $tempStationsJson) {
                        $webOutputJson = Get-Content $tempStationsJson | ConvertFrom-Json
                        $webOutputCount = if ($webOutputJson.stations) { $webOutputJson.stations.Count } else { 0 }
                        Write-Log "  temp stations.json has $webOutputCount stations" "Yellow"
                        if ($webOutputCount -gt 1) {
                            Copy-Item -Path $tempStationsJson -Destination "data/stations.json" -Force
                            Write-Log "Re-copied stations.json from temp file" "Green"
                        } else {
                            throw "temp stations.json also has wrong format ($webOutputCount stations)"
                        }
                    } else {
                        # Fallback: try temp web_output directory
                        $repoRoot = (Get-Location).Path
                        $parentDir = Split-Path -Parent $repoRoot
                        $tempWebOutput = Join-Path $parentDir "web_output_temp_deploy_$(Split-Path -Leaf $repoRoot)"
                        if (Test-Path "$tempWebOutput/data/stations.json") {
                            $webOutputJson = Get-Content "$tempWebOutput/data/stations.json" | ConvertFrom-Json
                            $webOutputCount = if ($webOutputJson.stations) { $webOutputJson.stations.Count } else { 0 }
                            Write-Log "  temp web_output has $webOutputCount stations" "Yellow"
                            if ($webOutputCount -gt 1) {
                                Copy-Item -Path "$tempWebOutput/data/stations.json" -Destination "data/stations.json" -Force
                                Write-Log "Re-copied stations.json from temp web_output" "Green"
                            } else {
                                throw "temp web_output also has wrong format ($webOutputCount stations)"
                            }
                        } else {
                            throw "Neither temp stations.json nor temp web_output found - cannot fix"
                        }
                    }
                } else {
                    Write-Log "Verified: stations.json has correct format ($stationCount stations)" "Green"
                }
            } catch {
                Write-Log "WARNING: Could not verify stations.json content: $_" "Yellow"
            }
            
            # Create/update .gitignore to exclude web_output directory
            if (-not (Test-Path ".gitignore")) {
                New-Item -Path ".gitignore" -ItemType File -Force | Out-Null
            }
            $gitignoreContent = Get-Content ".gitignore" -ErrorAction SilentlyContinue
            if ($gitignoreContent -notcontains "web_output/") {
                Add-Content -Path ".gitignore" -Value "web_output/"
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
        
        # Stage all files at root (excluding web_output directory itself)
        Write-Log "Staging files..." "Yellow"
        # Stage .gitignore first to ensure web_output is ignored
        if (Test-Path ".gitignore") {
            git add -f .gitignore 2>&1 | Out-Null
        }
        # Use git add with . to add all files, then unstage web_output if it exists
        git add -f . 2>&1 | Out-Null
        # Remove web_output from staging (we don't want the folder, just its contents at root)
        git reset HEAD web_output/ 2>&1 | Out-Null
        
        # Verify critical files are staged and have correct content
        $stagedFiles = git diff --cached --name-only
        $criticalFiles = @('index.html', 'data/stations.json', 'static/app.js', 'static/style.css')
        $missingFiles = @()
        foreach ($file in $criticalFiles) {
            if (-not ($stagedFiles -contains $file)) {
                $missingFiles += $file
            }
        }
        if ($missingFiles.Count -gt 0) {
            Write-Log "WARNING: Missing critical files in staging: $($missingFiles -join ', ')" "Yellow"
            Write-Log "Attempting to stage missing files..." "Yellow"
            foreach ($file in $missingFiles) {
                if (Test-Path $file) {
                    git add -f $file 2>&1 | Out-Null
                    Write-Log "  Staged: $file" "Green"
                } else {
                    Write-Log "  ERROR: $file does not exist!" "Red"
                }
            }
        } else {
            Write-Log "All critical files are staged" "Green"
        }
        
        # Final verification: Check that staged stations.json has correct format
        if (Test-Path "data/stations.json") {
            try {
                $stagedJson = Get-Content "data/stations.json" | ConvertFrom-Json
                $stagedCount = if ($stagedJson.stations) { $stagedJson.stations.Count } else { 0 }
                $stagedHasDates = $stagedJson.available_dates -ne $null
                
                if ($stagedCount -le 1 -or -not $stagedHasDates) {
                    Write-Log "ERROR: Staged stations.json still has old format! ($stagedCount stations, dates: $stagedHasDates)" "Red"
                    Write-Log "Re-copying from temp stations.json file..." "Yellow"
                    # Use absolute path in parent directory
                    $repoRoot = (Get-Location).Path
                    $parentDir = Split-Path -Parent $repoRoot
                    $tempStationsJson = Join-Path $parentDir "stations_json_temp_$(Split-Path -Leaf $repoRoot).json"
                    if (Test-Path $tempStationsJson) {
                        Copy-Item -Path $tempStationsJson -Destination "data/stations.json" -Force
                        git add -f "data/stations.json" 2>&1 | Out-Null
                        Write-Log "Re-copied and re-staged stations.json from temp file" "Green"
                    } elseif (Test-Path "web_output/data/stations.json") {
                        Copy-Item -Path "web_output/data/stations.json" -Destination "data/stations.json" -Force
                        git add -f "data/stations.json" 2>&1 | Out-Null
                        Write-Log "Re-copied and re-staged stations.json from web_output" "Green"
                    } else {
                        throw "Cannot fix: Neither temp stations.json nor web_output/data/stations.json found"
                    }
                } else {
                    Write-Log "Final verification: Staged stations.json is correct ($stagedCount stations)" "Green"
                }
            } catch {
                Write-Log "WARNING: Could not verify staged stations.json: $_" "Yellow"
            }
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
    # Force push to ensure old files are overwritten and cache is cleared
    Write-Log "Using force push to overwrite any cached content..." "Yellow"
    $pushOutput = git push -u origin $GITHUB_BRANCH --force 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Push output: $pushOutput" "Red"
        # Check if it's a remote URL issue
        if ($pushOutput -match "does not appear to be a git repository") {
            Write-Log "ERROR: Remote URL is incorrect. Current remote:" "Red"
            git remote -v 2>&1 | Write-Host
            Write-Log "Attempting to fix remote URL..." "Yellow"
            # Always use the normalized full URL
            git remote set-url origin $expectedUrl
            Write-Log "Remote URL fixed to: $expectedUrl" "Yellow"
            Write-Log "Retrying push..." "Yellow"
            $pushOutput = git push -u origin $GITHUB_BRANCH --force 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to push to GitHub after fixing remote URL"
            }
        } else {
            throw "Failed to push to GitHub"
        }
    }
    
    # Clean up temp files before success message
    # Use absolute path in parent directory
    $repoRoot = (Get-Location).Path
    $parentDir = Split-Path -Parent $repoRoot
    $tempWebOutput = Join-Path $parentDir "web_output_temp_deploy_$(Split-Path -Leaf $repoRoot)"
    $tempStationsJson = Join-Path $parentDir "stations_json_temp_$(Split-Path -Leaf $repoRoot).json"
    if (Test-Path $tempWebOutput) {
        Write-Log "Cleaning up temp web_output directory..." "Yellow"
        Remove-Item $tempWebOutput -Recurse -Force -ErrorAction SilentlyContinue
        Write-Log "Temp directory cleaned up" "Green"
    }
    if (Test-Path $tempStationsJson) {
        Write-Log "Cleaning up temp stations.json file..." "Yellow"
        Remove-Item $tempStationsJson -Force -ErrorAction SilentlyContinue
        Write-Log "Temp file cleaned up" "Green"
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
        $siteUrl = "https://$username.github.io/$repoName"
        Write-Log "  $siteUrl" "Green"
    } else {
        $siteUrl = "https://$repoPath.github.io"
        Write-Log "  $siteUrl" "Green"
    }
    Write-Log "" "White"
    Write-Log "Deployment Notes:" "Cyan"
    Write-Log "  - GitHub Pages may take 1-2 minutes to update" "Yellow"
    Write-Log "  - If you see the old version, clear your browser cache:" "Yellow"
    Write-Log "    * Press Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)" "White"
    Write-Log "    * Or open in an incognito/private window" "White"
    Write-Log "  - The deployment includes today's data: $(Get-Date -Format 'yyyy-MM-dd')" "Green"
    Write-Log "" "White"
    
    # Switch back to original branch
    if ($currentBranch -and $currentBranch -ne $GITHUB_BRANCH) {
        Write-Log "Switching back to $currentBranch branch..." "Yellow"
        git checkout $currentBranch 2>&1 | Out-Null
        
        # Don't restore stashed changes - they may contain merge conflicts
        # Clear any stashes to prevent conflicts from being restored
        $stashList = git stash list 2>&1
        if ($stashList -match "Auto-stash before gh-pages deployment") {
            Write-Log "Clearing stashed changes to prevent merge conflicts..." "Yellow"
            git stash drop 2>&1 | Out-Null
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
    Write-Log "  6. Check remote URL: git remote -v" "White"
    
    # Try to switch back to original branch
    if ($currentBranch) {
        Write-Log "Switching back to $currentBranch branch..." "Yellow"
        git checkout $currentBranch 2>&1 | Out-Null
        
        # Clear any stashes to prevent merge conflicts from being restored
        $stashList = git stash list 2>&1
        if ($stashList -match "Auto-stash before gh-pages deployment") {
            Write-Log "Clearing stashed changes to prevent merge conflicts..." "Yellow"
            git stash drop 2>&1 | Out-Null
        }
    }
    exit 1
}
